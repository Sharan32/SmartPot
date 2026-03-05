#!/bin/bash

echo "===================================="
echo "FirmPot Environment Verification"
echo "===================================="

check_cmd () {
    if command -v $1 &> /dev/null
    then
        echo "[OK] $1 installed"
    else
        echo "[MISSING] $1 NOT installed"
    fi
}

echo ""
echo "---- Basic Tools ----"
check_cmd git
check_cmd wget
check_cmd python3
check_cmd pip3

echo ""
echo "---- QEMU Emulators ----"
check_cmd qemu-mips-static
check_cmd qemu-arm-static
check_cmd qemu-aarch64-static

echo ""
echo "---- binfmt_misc ----"
if [ -d "/proc/sys/fs/binfmt_misc" ]; then
    echo "[OK] binfmt_misc directory exists"
else
    echo "[MISSING] binfmt_misc not available"
fi

echo ""
echo "---- Binwalk ----"
check_cmd binwalk

echo ""
echo "---- Firmware Extraction Tools ----"
check_cmd sasquatch
check_cmd jefferson
check_cmd ubireader_extract_files

echo ""
echo "---- Selenium / WebDriver ----"
check_cmd geckodriver

echo ""
echo "---- Python Libraries ----"

python3 - <<EOF
modules = [
"numpy",
"tensorflow",
"sklearn",
"gensim",
"xxhash",
"neologdn",
"simstring",
"paramiko",
"pandas",
"flask",
"dash",
"pygeoip",
"seleniumwire"
]

for m in modules:
    try:
        __import__(m)
        print(f"[OK] {m}")
    except:
        print(f"[MISSING] {m}")
EOF

echo ""
echo "---- GeoIP Data ----"
if [ -f "./utils/files/GeoLiteCity.dat" ]; then
    echo "[OK] GeoLiteCity.dat present"
else
    echo "[MISSING] GeoLiteCity.dat missing"
fi

echo ""
echo "---- FirmPot Folders ----"

if [ -d "images" ]; then
    echo "[OK] images folder exists"
else
    echo "[MISSING] images folder"
fi

if [ -d "tools" ]; then
    echo "[OK] tools folder exists"
else
    echo "[MISSING] tools folder"
fi

echo ""
echo "===================================="
echo "Verification Complete"
echo "===================================="
