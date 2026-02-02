@echo off
IF NOT EXIST venv (
    echo Creating virtual environment...
    python -m venv venv
)

echo Activating virtual environment...
call venv\Scripts\activate

echo Upgrading pip...
python -m pip install --upgrade pip

echo Installing dependencies...
pip install --upgrade -r requirements.txt

echo Starting sojbot-3000...
set PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python
python main.py
pause
