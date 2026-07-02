@echo off
venv\Scripts\python.exe _dev_scripts\dump_diag.py > dump_out.txt 2>&1
echo Done > done.txt
