@echo off
echo Starting MongoDB...
tasklist /FI "IMAGENAME eq mongod.exe" 2>NUL | find /I /N "mongod.exe">NUL
if "%ERRORLEVEL%"=="1" (
    start "" "C:\Program Files\MongoDB\Server\8.2\bin\mongod.exe" --dbpath "C:\Users\sarch\mongodb-data" --port 27017 --logpath "C:\Users\sarch\mongodb-log\mongod.log" --logappend
    timeout /t 4 /nobreak >NUL
    echo MongoDB started.
) else (
    echo MongoDB already running.
)

echo Starting backend...
uvicorn server:app --host 0.0.0.0 --port 8000
