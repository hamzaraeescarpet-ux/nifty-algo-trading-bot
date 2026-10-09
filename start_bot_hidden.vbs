Set WshShell = CreateObject("WScript.Shell")
Dim fso, scriptDir
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = scriptDir
WshShell.Run "python run_bot.py", 0, False
