@echo off
rem Starts SubSync from this source tree (see doc/assets.md)
start "" "%~dp0.py36\pythonw.exe" "%~dp0run.py" %*
