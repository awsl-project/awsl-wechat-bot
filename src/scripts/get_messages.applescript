-- WeChat 消息提取器 - 通过 Accessibility API
-- 直接获取聊天消息文本

on detectWeChatProcess()
	set processNames to {"WeChat", "微信"}
	repeat with procName in processNames
		tell application "System Events"
			if exists (process procName) then
				return procName
			end if
		end tell
	end repeat
	return missing value
end detectWeChatProcess

-- 查找消息列表元素
on findMessagesList(elem, depth, maxDepth)
	if depth > maxDepth then
		return missing value
	end if

	try
		tell application "System Events"
			-- 检查当前元素是否是消息列表
			set elemRole to role of elem
			if elemRole is "AXList" then
				try
					set elemTitle to title of elem
					if elemTitle is "Messages" then
						return elem
					end if
				end try
			end if

			-- 递归搜索子元素
			try
				set children to UI elements of elem
				repeat with child in children
					set foundList to my findMessagesList(child, depth + 1, maxDepth)
					if foundList is not missing value then
						return foundList
					end if
				end repeat
			end try
		end tell
	end try

	return missing value
end findMessagesList

-- 从消息列表中提取所有消息
on extractMessages(messagesList)
	set messages to {}

	try
		tell application "System Events"
			set messageElements to UI elements of messagesList

			repeat with msgElem in messageElements
				try
					-- 获取 title 属性（消息文本存储在这里）
					set msgTitle to title of msgElem
					if msgTitle is not missing value and msgTitle is not "" then
						set end of messages to msgTitle
					end if
				end try
			end repeat
		end tell
	end try

	return messages
end extractMessages

-- 主程序
on run
	set wechatProcess to detectWeChatProcess()
	if wechatProcess is missing value then
		return "ERROR: 微信未运行"
	end if

	try
		tell application "System Events"
			tell process wechatProcess
				set frontmost to true
				delay 0.3

				if (count of windows) > 0 then
					set mainWindow to window 1

					-- 查找消息列表（优化：降低递归深度从15到10）
					set messagesList to my findMessagesList(mainWindow, 0, 10)

					if messagesList is not missing value then
						-- 提取所有消息
						set messages to my extractMessages(messagesList)

						if (count of messages) > 0 then
							-- 返回消息，用特殊分隔符分隔
							set AppleScript's text item delimiters to "|||"
							return "SUCCESS:" & (messages as text)
						else
							return "SUCCESS:NO_MESSAGES"
						end if
					else
						return "ERROR: 未找到消息列表"
					end if
				else
					return "ERROR: 没有窗口"
				end if
			end tell
		end tell
	on error errMsg
		return "ERROR: " & errMsg
	end try
end run
