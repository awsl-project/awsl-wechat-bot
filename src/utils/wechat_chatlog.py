#!/usr/bin/env python3
"""
微信聊天记录工具

功能:
1. 解密加密的微信数据库 (V4 版本)
2. 列出群聊名称
3. 按时间范围查询聊天记录

使用方法:
    python wechat_chatlog.py decrypt --input <目录> --key <密钥> --output <输出目录>
    python wechat_chatlog.py list-groups --db-path <解密后目录>
    python wechat_chatlog.py query --db-path <目录> --group <群ID> [--start <时间>] [--end <时间>]
"""

import argparse
import hashlib
import hmac
import json
import os
import re
import shutil
import sqlite3
import struct
from dataclasses import dataclass
from datetime import datetime
from hashlib import pbkdf2_hmac, sha512
from typing import Optional

try:
    from Crypto.Cipher import AES
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

try:
    import zstandard as zstd
    HAS_ZSTD = True
except ImportError:
    HAS_ZSTD = False

# ============================================================
# 常量
# ============================================================

KEY_SIZE = 32
SALT_SIZE = 16
IV_SIZE = 16
PAGE_SIZE = 4096
ITER_COUNT = 256000
HMAC_SHA512_SIZE = 64
AES_BLOCK_SIZE = 16
SQLITE_HEADER = b"SQLite format 3\x00"

_reserve = IV_SIZE + HMAC_SHA512_SIZE
RESERVE_SIZE = ((_reserve // AES_BLOCK_SIZE) + 1) * AES_BLOCK_SIZE if _reserve % AES_BLOCK_SIZE != 0 else _reserve

MESSAGE_TYPE_TEXT = 1
MESSAGE_TYPE_IMAGE = 3
MESSAGE_TYPE_VOICE = 34
MESSAGE_TYPE_VIDEO = 43
MESSAGE_TYPE_ANIMATION = 47
MESSAGE_TYPE_LOCATION = 48
MESSAGE_TYPE_SHARE = 49
MESSAGE_TYPE_SYSTEM = 10000


# ============================================================
# 数据模型
# ============================================================

@dataclass
class ChatRoom:
    """群聊信息"""
    username: str
    owner: str
    remark: str = ""
    nick_name: str = ""
    user_display_names: dict = None  # username -> display_name 映射

    def __post_init__(self):
        if self.user_display_names is None:
            self.user_display_names = {}

    def display_name(self) -> str:
        return self.remark or self.nick_name or self.username

    def to_dict(self) -> dict:
        return {
            "username": self.username,
            "owner": self.owner,
            "remark": self.remark,
            "nick_name": self.nick_name,
            "display_name": self.display_name()
        }


@dataclass
class Message:
    """消息"""
    seq: int
    time: datetime
    talker: str
    sender: str
    sender_name: str
    msg_type: int
    content: str
    is_self: bool = False

    def format(self, time_format: str = "%Y-%m-%d %H:%M:%S") -> str:
        sender_display = "我" if self.is_self else (self.sender_name or self.sender)
        return f"[{self.time.strftime(time_format)}] {sender_display}: {self.content}"

    def to_dict(self) -> dict:
        return {
            "seq": self.seq,
            "time": self.time.isoformat(),
            "talker": self.talker,
            "sender": self.sender,
            "sender_name": self.sender_name,
            "msg_type": self.msg_type,
            "content": self.content,
            "is_self": self.is_self
        }


# ============================================================
# 解密器
# ============================================================

class WeChatDBDecryptor:
    """微信数据库解密器 (V4 版本)"""

    def __init__(self, key_hex: str):
        if not HAS_CRYPTO:
            raise ImportError("需要 pycryptodome: pip install pycryptodome")
        self.key = bytes.fromhex(key_hex)
        if len(self.key) != KEY_SIZE:
            raise ValueError(f"密钥长度必须是 {KEY_SIZE} 字节 ({KEY_SIZE * 2} 个十六进制字符)")

    def _derive_keys(self, salt: bytes) -> tuple[bytes, bytes]:
        enc_key = pbkdf2_hmac('sha512', self.key, salt, ITER_COUNT, KEY_SIZE)
        mac_salt = bytes(b ^ 0x3a for b in salt)
        mac_key = pbkdf2_hmac('sha512', enc_key, mac_salt, 2, KEY_SIZE)
        return enc_key, mac_key

    def _validate_key(self, first_page: bytes) -> bool:
        if len(first_page) < PAGE_SIZE:
            return False
        salt = first_page[:SALT_SIZE]
        _, mac_key = self._derive_keys(salt)
        data_end = PAGE_SIZE - RESERVE_SIZE + IV_SIZE
        h = hmac.new(mac_key, digestmod=sha512)
        h.update(first_page[SALT_SIZE:data_end])
        h.update(struct.pack('<I', 1))
        return hmac.compare_digest(h.digest(), first_page[data_end:data_end + HMAC_SHA512_SIZE])

    def _decrypt_page(self, page_buf: bytes, enc_key: bytes, mac_key: bytes, page_num: int) -> bytes:
        offset = SALT_SIZE if page_num == 0 else 0
        data_end = PAGE_SIZE - RESERVE_SIZE + IV_SIZE
        h = hmac.new(mac_key, digestmod=sha512)
        h.update(page_buf[offset:data_end])
        h.update(struct.pack('<I', page_num + 1))
        if not hmac.compare_digest(h.digest(), page_buf[data_end:data_end + HMAC_SHA512_SIZE]):
            raise ValueError(f"页 {page_num} HMAC 验证失败")
        iv = page_buf[PAGE_SIZE - RESERVE_SIZE:PAGE_SIZE - RESERVE_SIZE + IV_SIZE]
        cipher = AES.new(enc_key, AES.MODE_CBC, iv)
        decrypted = cipher.decrypt(page_buf[offset:PAGE_SIZE - RESERVE_SIZE])
        return decrypted + page_buf[PAGE_SIZE - RESERVE_SIZE:]

    def decrypt_file(self, input_path: str, output_path: str) -> bool:
        """解密单个数据库文件"""
        with open(input_path, 'rb') as f:
            first_page = f.read(PAGE_SIZE)

        if first_page[:len(SQLITE_HEADER) - 1] == SQLITE_HEADER[:-1]:
            print(f"  跳过 (已解密): {input_path}")
            shutil.copy2(input_path, output_path)
            return True

        if not self._validate_key(first_page):
            print(f"  失败 (密钥无效): {input_path}")
            return False

        salt = first_page[:SALT_SIZE]
        enc_key, mac_key = self._derive_keys(salt)
        file_size = os.path.getsize(input_path)
        total_pages = (file_size + PAGE_SIZE - 1) // PAGE_SIZE

        with open(input_path, 'rb') as fin, open(output_path, 'wb') as fout:
            fout.write(SQLITE_HEADER)
            for page_num in range(total_pages):
                page_buf = fin.read(PAGE_SIZE)
                if not page_buf:
                    break
                if len(page_buf) < PAGE_SIZE:
                    page_buf = page_buf + b'\x00' * (PAGE_SIZE - len(page_buf))
                if all(b == 0 for b in page_buf):
                    fout.write(page_buf)
                    continue
                try:
                    fout.write(self._decrypt_page(page_buf, enc_key, mac_key, page_num))
                except Exception as e:
                    print(f"  警告: 页 {page_num} 解密失败: {e}")
                    fout.write(page_buf)

        print(f"  成功: {input_path} -> {output_path}")
        return True

    def decrypt_directory(self, input_dir: str, output_dir: str) -> int:
        """解密目录下的所有数据库文件"""
        os.makedirs(output_dir, exist_ok=True)
        success_count = 0

        # message 数据库
        message_dir = os.path.join(input_dir, "db_storage", "message")
        if os.path.isdir(message_dir):
            for filename in os.listdir(message_dir):
                if re.match(r'^message_\d*\.db$', filename):
                    input_path = os.path.join(message_dir, filename)
                    if os.path.isfile(input_path) and self.decrypt_file(input_path, os.path.join(output_dir, filename)):
                        success_count += 1

        # contact 数据库
        contact_db = os.path.join(input_dir, "db_storage", "contact", "contact.db")
        if os.path.isfile(contact_db) and self.decrypt_file(contact_db, os.path.join(output_dir, "contact.db")):
            success_count += 1

        return success_count


# ============================================================
# Protobuf 解析 (RoomData)
# ============================================================

def _parse_varint(data: bytes, pos: int) -> tuple[int, int]:
    """解析 varint，返回 (值, 新位置)"""
    result = 0
    shift = 0
    while pos < len(data):
        b = data[pos]
        result |= (b & 0x7f) << shift
        pos += 1
        if (b & 0x80) == 0:
            break
        shift += 7
    return result, pos


def _parse_room_data(ext_buffer: bytes) -> dict[str, str]:
    """
    解析 chat_room.ext_buffer 中的 protobuf 数据，提取群成员昵称

    Returns:
        dict: username -> display_name 映射
    """
    if not ext_buffer or len(ext_buffer) < 2:
        return {}

    user_display_names = {}
    pos = 0

    try:
        while pos < len(ext_buffer):
            if pos >= len(ext_buffer):
                break

            # 读取 field tag
            tag, pos = _parse_varint(ext_buffer, pos)
            field_number = tag >> 3
            wire_type = tag & 0x07

            if wire_type == 0:  # varint
                _, pos = _parse_varint(ext_buffer, pos)
            elif wire_type == 2:  # length-delimited
                length, pos = _parse_varint(ext_buffer, pos)
                if pos + length > len(ext_buffer):
                    break

                if field_number == 1:  # users 字段
                    user_data = ext_buffer[pos:pos + length]
                    user_info = _parse_room_data_user(user_data)
                    if user_info and user_info[0] and user_info[1]:
                        user_display_names[user_info[0]] = user_info[1]

                pos += length
            else:
                break
    except Exception:
        pass

    return user_display_names


def _parse_room_data_user(data: bytes) -> tuple[str, str]:
    """
    解析 RoomDataUser protobuf

    Returns:
        tuple: (username, display_name)
    """
    username = ""
    display_name = ""
    pos = 0

    try:
        while pos < len(data):
            tag, pos = _parse_varint(data, pos)
            field_number = tag >> 3
            wire_type = tag & 0x07

            if wire_type == 0:  # varint
                _, pos = _parse_varint(data, pos)
            elif wire_type == 2:  # length-delimited (string)
                length, pos = _parse_varint(data, pos)
                if pos + length > len(data):
                    break

                value = data[pos:pos + length].decode('utf-8', errors='ignore')

                if field_number == 1:  # userName
                    username = value
                elif field_number == 2:  # displayName
                    display_name = value

                pos += length
            else:
                break
    except Exception:
        pass

    return username, display_name


# ============================================================
# 读取器
# ============================================================

class WeChatDBReader:
    """微信数据库读取器"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._contact_db: Optional[sqlite3.Connection] = None
        self._message_dbs: dict[str, sqlite3.Connection] = {}
        self._message_db_times: list[tuple[str, int, int]] = []
        self._chatroom_display_names: dict[str, dict[str, str]] = {}  # chatroom -> {username -> display_name}

    def _find_db_files(self, pattern: str) -> list[str]:
        files = []
        regex = re.compile(pattern)
        for f in os.listdir(self.db_path):
            if regex.match(f):
                files.append(os.path.join(self.db_path, f))
        return sorted(files)

    def _get_contact_db(self) -> sqlite3.Connection:
        if self._contact_db is None:
            db_path = os.path.join(self.db_path, "contact.db")
            if not os.path.exists(db_path):
                raise FileNotFoundError(f"联系人数据库不存在: {db_path}")
            self._contact_db = sqlite3.connect(db_path)
        return self._contact_db

    def _init_message_dbs(self) -> None:
        if self._message_db_times:
            return
        db_files = self._find_db_files(r"^message_([0-9]?[0-9])?\.db$")
        infos = []
        for db_path in db_files:
            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT timestamp FROM Timestamp LIMIT 1")
                row = cursor.fetchone()
                if row:
                    infos.append((db_path, row[0]))
                conn.close()
            except Exception as e:
                print(f"警告: 无法读取数据库 {db_path}: {e}")
        infos.sort(key=lambda x: x[1])
        self._message_db_times = []
        for i, (path, start_time) in enumerate(infos):
            end_time = infos[i + 1][1] if i < len(infos) - 1 else int(datetime.now().timestamp()) + 3600
            self._message_db_times.append((path, start_time, end_time))

    def _get_message_db(self, db_path: str) -> sqlite3.Connection:
        if db_path not in self._message_dbs:
            self._message_dbs[db_path] = sqlite3.connect(db_path)
        return self._message_dbs[db_path]

    def _get_dbs_for_time_range(self, start_time: int, end_time: int) -> list[str]:
        self._init_message_dbs()
        return [p for p, s, e in self._message_db_times if s < end_time and e > start_time]

    def _talker_to_table_name(self, talker: str) -> str:
        return f"Msg_{hashlib.md5(talker.encode()).hexdigest()}"

    def _decompress_content(self, content: bytes) -> str:
        if content and len(content) >= 4 and content[:4] == b'\x28\xb5\x2f\xfd' and HAS_ZSTD:
            try:
                return zstd.ZstdDecompressor().decompress(content).decode('utf-8')
            except Exception:
                pass
        return content.decode('utf-8', errors='ignore') if isinstance(content, bytes) else str(content)

    def list_groups(self, limit: int = 0) -> list[ChatRoom]:
        """列出所有群聊"""
        db = self._get_contact_db()
        cursor = db.cursor()
        query = "SELECT username, owner FROM chat_room ORDER BY username"
        if limit > 0:
            query += f" LIMIT {limit}"
        cursor.execute(query)
        chat_rooms = []
        for username, owner in cursor.fetchall():
            chat_room = ChatRoom(username=username, owner=owner or "")
            cursor.execute("SELECT nick_name, remark FROM contact WHERE username = ?", (username,))
            row = cursor.fetchone()
            if row:
                chat_room.nick_name = row[0] or ""
                chat_room.remark = row[1] or ""
            chat_rooms.append(chat_room)
        return chat_rooms

    def get_group_display_name(self, group_id: str) -> str:
        """获取群聊显示名称（优先 remark，其次 nick_name）"""
        db = self._get_contact_db()
        cursor = db.cursor()
        cursor.execute("SELECT nick_name, remark FROM contact WHERE username = ?", (group_id,))
        row = cursor.fetchone()
        if row:
            return row[1] or row[0] or group_id
        return group_id

    def get_contact_name(self, username: str) -> str:
        """获取联系人名称"""
        db = self._get_contact_db()
        cursor = db.cursor()
        cursor.execute("SELECT nick_name, remark, alias FROM contact WHERE username = ?", (username,))
        row = cursor.fetchone()
        if row:
            return row[1] or row[0] or row[2] or username
        return username

    def _get_chatroom_display_names(self, chatroom: str) -> dict[str, str]:
        """获取群成员的群昵称映射"""
        if chatroom in self._chatroom_display_names:
            return self._chatroom_display_names[chatroom]

        display_names = {}
        try:
            db = self._get_contact_db()
            cursor = db.cursor()
            cursor.execute("SELECT ext_buffer FROM chat_room WHERE username = ?", (chatroom,))
            row = cursor.fetchone()
            if row and row[0]:
                display_names = _parse_room_data(row[0])
        except Exception:
            pass

        self._chatroom_display_names[chatroom] = display_names
        return display_names

    def get_messages(
        self,
        talker: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        text_only: bool = True,
        limit: int = 0,
        offset: int = 0
    ) -> list[Message]:
        """获取聊天记录"""
        start_time = start_time or datetime(2000, 1, 1)
        end_time = end_time or datetime.now()
        start_ts, end_ts = int(start_time.timestamp()), int(end_time.timestamp())

        db_paths = self._get_dbs_for_time_range(start_ts, end_ts)
        if not db_paths:
            return []

        table_name = self._talker_to_table_name(talker)
        is_chatroom = talker.endswith("@chatroom")
        messages = []

        # 获取群昵称映射
        display_names = self._get_chatroom_display_names(talker) if is_chatroom else {}

        for db_path in db_paths:
            db = self._get_message_db(db_path)
            cursor = db.cursor()
            cursor.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
            if not cursor.fetchone():
                continue

            query = f"""
                SELECT m.sort_seq, m.server_id, m.local_type, n.user_name,
                       m.create_time, m.message_content, m.status
                FROM {table_name} m
                LEFT JOIN Name2Id n ON m.real_sender_id = n.rowid
                WHERE m.create_time >= ? AND m.create_time <= ?
                ORDER BY m.sort_seq ASC
            """
            cursor.execute(query, (start_ts, end_ts))

            for sort_seq, server_id, local_type, user_name, create_time, message_content, status in cursor.fetchall():
                msg_type = local_type & 0xFFFFFFFF
                if text_only and msg_type != MESSAGE_TYPE_TEXT:
                    continue

                content = self._decompress_content(message_content) if message_content else ""
                sender = user_name or ""

                if is_chatroom and ":\n" in content:
                    parts = content.split(":\n", 1)
                    if len(parts) == 2:
                        sender, content = parts

                is_self = status == 2 or (not is_chatroom and talker != sender)
                # 优先使用群昵称，其次使用联系人名称
                sender_name = display_names.get(sender) or self.get_contact_name(sender) if sender else ""

                messages.append(Message(
                    seq=sort_seq,
                    time=datetime.fromtimestamp(create_time),
                    talker=talker,
                    sender=sender,
                    sender_name=sender_name,
                    msg_type=msg_type,
                    content=content,
                    is_self=is_self
                ))

        messages.sort(key=lambda m: m.seq)
        if offset > 0:
            messages = messages[offset:]
        if limit > 0:
            messages = messages[:limit]
        return messages

    def close(self) -> None:
        if self._contact_db:
            self._contact_db.close()
        for conn in self._message_dbs.values():
            conn.close()


# ============================================================
# CLI 命令
# ============================================================

def cmd_decrypt(args) -> int:
    """解密命令"""
    if not HAS_CRYPTO:
        print("缺少依赖: pip install pycryptodome")
        return 1
    if not os.path.isdir(args.input):
        print(f"错误: 目录不存在: {args.input}")
        return 1

    print(f"开始解密...")
    print(f"输入: {args.input}")
    print(f"输出: {args.output}\n")

    try:
        decryptor = WeChatDBDecryptor(args.key)
        count = decryptor.decrypt_directory(args.input, args.output)
        print(f"\n完成! 成功解密 {count} 个文件")
        return 0
    except Exception as e:
        print(f"解密失败: {e}")
        return 1


def cmd_list_groups(args) -> int:
    """列出群聊命令"""
    if not os.path.isdir(args.db_path):
        print(f"错误: 目录不存在: {args.db_path}")
        return 1

    reader = WeChatDBReader(args.db_path)
    try:
        groups = reader.list_groups(limit=args.limit)
        if not groups:
            print("没有找到群聊")
            return 0

        if args.json:
            print(json.dumps([g.to_dict() for g in groups], ensure_ascii=False, indent=2))
        else:
            print(f"共找到 {len(groups)} 个群聊:\n")
            for i, g in enumerate(groups, 1):
                display = g.display_name()
                if display != g.username:
                    print(f"{i:4}. {display} ({g.username})")
                else:
                    print(f"{i:4}. {g.username}")
        return 0
    finally:
        reader.close()


def cmd_query(args) -> int:
    """查询消息命令"""
    if not os.path.isdir(args.db_path):
        print(f"错误: 目录不存在: {args.db_path}")
        return 1

    start_time = end_time = None
    try:
        if args.start:
            fmt = "%Y-%m-%d %H:%M:%S" if " " in args.start else "%Y-%m-%d"
            start_time = datetime.strptime(args.start, fmt)
        if args.end:
            fmt = "%Y-%m-%d %H:%M:%S" if " " in args.end else "%Y-%m-%d"
            end_time = datetime.strptime(args.end, fmt)
            if " " not in args.end:
                end_time = end_time.replace(hour=23, minute=59, second=59)
    except ValueError as e:
        print(f"错误: 无效的时间格式: {e}")
        return 1

    reader = WeChatDBReader(args.db_path)
    try:
        messages = reader.get_messages(
            talker=args.group,
            start_time=start_time,
            end_time=end_time,
            text_only=True,
            limit=args.limit
        )

        if not messages:
            print("没有找到消息")
            return 0

        if args.json:
            print(json.dumps([m.to_dict() for m in messages], ensure_ascii=False, indent=2))
        else:
            print(f"共 {len(messages)} 条消息:\n")
            for msg in messages:
                print(msg.format())

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                if args.json:
                    json.dump([m.to_dict() for m in messages], f, ensure_ascii=False, indent=2)
                else:
                    for msg in messages:
                        f.write(msg.format() + "\n")
            print(f"\n已保存到: {args.output}")

        return 0
    finally:
        reader.close()


def main():
    parser = argparse.ArgumentParser(
        description="微信聊天记录工具",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # decrypt 命令
    p_decrypt = subparsers.add_parser("decrypt", help="解密微信数据库")
    p_decrypt.add_argument("--input", "-i", required=True, help="加密数据库目录 (DataDir)")
    p_decrypt.add_argument("--key", "-k", required=True, help="32字节密钥的十六进制字符串")
    p_decrypt.add_argument("--output", "-o", required=True, help="解密输出目录")

    # list-groups 命令
    p_list = subparsers.add_parser("list-groups", help="列出所有群聊")
    p_list.add_argument("--db-path", "-d", required=True, help="解密后的数据库目录")
    p_list.add_argument("--limit", "-n", type=int, default=0, help="限制返回数量")
    p_list.add_argument("--json", "-j", action="store_true", help="输出 JSON 格式")

    # query 命令
    p_query = subparsers.add_parser("query", help="查询聊天记录")
    p_query.add_argument("--db-path", "-d", required=True, help="解密后的数据库目录")
    p_query.add_argument("--group", "-g", required=True, help="群聊ID 或个人微信ID")
    p_query.add_argument("--start", "-s", help="开始时间 (YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS)")
    p_query.add_argument("--end", "-e", help="结束时间 (YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS)")
    p_query.add_argument("--limit", "-n", type=int, default=0, help="限制返回数量")
    p_query.add_argument("--output", "-o", help="输出到文件")
    p_query.add_argument("--json", "-j", action="store_true", help="输出 JSON 格式")

    args = parser.parse_args()

    if args.command == "decrypt":
        return cmd_decrypt(args)
    elif args.command == "list-groups":
        return cmd_list_groups(args)
    elif args.command == "query":
        return cmd_query(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    exit(main())
