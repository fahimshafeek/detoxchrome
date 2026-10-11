import sys
import json
import subprocess
import os

ADDICTIVE_AND_BLOATWARE = [
    # System & Store
    {"id": "com.android.vending", "name": "Google Play Store", "category": "System"},
    {"id": "com.google.android.packageinstaller", "name": "Google Package Installer", "category": "System"},
    {"id": "com.android.packageinstaller", "name": "Package Installer", "category": "System"},
    {"id": "com.samsung.android.bixby.agent", "name": "Bixby Agent", "category": "System"},
    {"id": "com.samsung.android.bixby.wakeup", "name": "Bixby Wakeup", "category": "System"},
    
    # Browsers
    {"id": "com.android.chrome", "name": "Google Chrome", "category": "Browsers"},
    {"id": "org.chromium.chrome", "name": "Chromium", "category": "Browsers"},

    # Social & Communication
    {"id": "com.instagram.android", "name": "Instagram", "category": "Social"},
    {"id": "com.instagram.barcelona", "name": "Threads", "category": "Social"},
    {"id": "com.facebook.katana", "name": "Facebook", "category": "Social"},
    {"id": "com.facebook.system", "name": "Facebook System", "category": "Social"},
    {"id": "com.facebook.appmanager", "name": "Facebook App Manager", "category": "Social"},
    {"id": "com.facebook.services", "name": "Facebook Services", "category": "Social"},
    {"id": "com.facebook.orca", "name": "Messenger", "category": "Social"},
    {"id": "com.twitter.android", "name": "X / Twitter", "category": "Social"},
    {"id": "com.snapchat.android", "name": "Snapchat", "category": "Social"},
    {"id": "com.zhiliaoapp.musically", "name": "TikTok", "category": "Social"},
    {"id": "com.reddit.frontpage", "name": "Reddit", "category": "Social"},
    {"id": "com.discord", "name": "Discord", "category": "Social"},
    {"id": "org.telegram.messenger", "name": "Telegram", "category": "Social"},
    {"id": "com.whatsapp", "name": "WhatsApp", "category": "Social"},
    {"id": "com.pinterest", "name": "Pinterest", "category": "Social"},

    # Media & Entertainment
    {"id": "com.google.android.youtube", "name": "YouTube", "category": "Media"},
    {"id": "com.google.android.apps.youtube.music", "name": "YouTube Music", "category": "Media"},
    {"id": "com.spotify.music", "name": "Spotify", "category": "Media"},
    {"id": "com.netflix.mediaclient", "name": "Netflix", "category": "Media"},
    {"id": "in.startv.hotstar", "name": "Disney+ Hotstar", "category": "Media"},
    {"id": "com.amazon.avod.thirdpartyclient", "name": "Prime Video", "category": "Media"},

    # Games
    {"id": "com.supercell.clashroyale", "name": "Clash Royale", "category": "Games"},
    {"id": "com.ea.games.r3_row", "name": "Real Racing 3", "category": "Games"},
    {"id": "com.dream11sportsguru", "name": "Dream11", "category": "Games"},

    # Productivity & Shopping
    {"id": "in.amazon.mShop.android.shopping", "name": "Amazon Shopping", "category": "Productivity"},
    {"id": "com.amazon.mShop.android.shopping", "name": "Amazon", "category": "Productivity"},
    {"id": "com.flipkart.android", "name": "Flipkart", "category": "Productivity"},
    {"id": "com.microsoft.office.word", "name": "Microsoft Word", "category": "Productivity"},
    {"id": "com.microsoft.office.excel", "name": "Microsoft Excel", "category": "Productivity"},
    {"id": "com.microsoft.office.powerpoint", "name": "Microsoft PowerPoint", "category": "Productivity"},
    {"id": "cn.wps.moffice_eng", "name": "WPS Office", "category": "Productivity"}
]

def run_adb(args):
    try:
        result = subprocess.run(["adb"] + args, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except Exception:
        return None

def get_device_info():
    devices_output = run_adb(["devices"])
    if not devices_output:
        return None
    
    serial = None
    lines = devices_output.strip().split("\n")[1:]
    for line in lines:
        parts = line.strip().split()
        if len(parts) >= 2 and parts[1] == "device":
            serial = parts[0]
            break
            
    if not serial:
        return None
        
    brand = run_adb(["shell", "getprop", "ro.product.brand"]) or ""
    model = run_adb(["shell", "getprop", "ro.product.model"]) or ""
    marketname = run_adb(["shell", "getprop", "ro.product.marketname"]) or ""
    
    device_name = f"{brand.capitalize()} {model}".strip()
    if marketname:
        device_name = f"{brand.capitalize()} {marketname}".strip()
    elif not device_name:
        device_name = serial

    return {
        "serial": serial,
        "name": device_name,
        "brand": brand,
        "model": model
    }

def get_status():
    dev = get_device_info()
    if not dev:
        return {"error": "No authorized ADB device found. Please connect your phone with USB debugging enabled."}

    installed_output = run_adb(["shell", "pm", "list", "packages"])
    if installed_output is None:
        return {"error": "Failed to read packages. Is device connected?"}
    
    installed_packages = set()
    for line in installed_output.split('\n'):
        if line.startswith("package:"):
            installed_packages.add(line.replace("package:", "").strip())
            
    response = []
    for app in ADDICTIVE_AND_BLOATWARE:
        is_installed = app["id"] in installed_packages
        response.append({
            "id": app["id"],
            "name": app["name"],
            "category": app.get("category", "Other"),
            "enabled": is_installed
        })
        
    return {
        "device": dev,
        "apps": response
    }

def toggle_app(package_id, enable):
    if enable == "1":
        res = run_adb(["shell", "cmd", "package", "install-existing", package_id])
    else:
        res = run_adb(["shell", "pm", "uninstall", "-k", "--user", "0", package_id])
    
    if res is None:
        return {"success": False, "error": "ADB command failed."}
    return {"success": True}

def find_apk_path():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(script_dir, "apk", "ChromePublic.apk"),
        os.path.join(script_dir, "..", "apk", "ChromePublic.apk"),
        os.path.join(script_dir, "ChromePublic.apk"),
        os.path.join(os.getcwd(), "apk", "ChromePublic.apk"),
        os.path.join(os.getcwd(), "ChromePublic.apk"),
        "/home/rohith/hack2/apk/ChromePublic.apk",
        "/home/rohith/hack2/ChromePublic.apk",
        "/home/rohith/Desktop/apk/ChromePublic.apk",
        "/home/rohith/Desktop/ChromePublic.apk",
        "/home/rohith/Downloads/Telegram Desktop/ChromePublic.apk",
    ]
    for c in candidates:
        norm = os.path.normpath(c)
        if os.path.isfile(norm):
            return norm
    return None

def install_apk(apk_path=None):
    if not apk_path:
        apk_path = find_apk_path()
    if not apk_path:
        return {"success": False, "error": "ChromePublic.apk not found. Please place it in apk/ folder."}

    dev = get_device_info()
    if not dev:
        return {"success": False, "error": "No authorized ADB device found. Please connect phone via USB."}

    try:
        proc = subprocess.run(["adb", "install", "-r", "-d", apk_path], capture_output=True, text=True, timeout=300)
        out = (proc.stdout + "\n" + proc.stderr).strip()
        if "Success" in out:
            return {"success": True, "message": "Detox Chromium APK installed successfully."}
        else:
            return {"success": False, "error": out or "Installation failed."}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "APK installation timed out."}
    except Exception as e:
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No command provided"}))
        sys.exit(1)
        
    cmd = sys.argv[1]
    if cmd == "status":
        print(json.dumps(get_status()))
    elif cmd == "device":
        dev = get_device_info()
        print(json.dumps(dev if dev else {"error": "No device"}))
    elif cmd == "toggle":
        if len(sys.argv) < 4:
            print(json.dumps({"error": "Missing arguments for toggle"}))
            sys.exit(1)
        pkg = sys.argv[2]
        enable = sys.argv[3]
        print(json.dumps(toggle_app(pkg, enable)))
    elif cmd == "install_apk":
        apk_arg = sys.argv[2] if len(sys.argv) > 2 else None
        print(json.dumps(install_apk(apk_arg)))
    else:
        print(json.dumps({"error": f"Unknown command {cmd}"}))

