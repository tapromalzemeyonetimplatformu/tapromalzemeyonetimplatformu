# auth.py

# Kullanıcı adı - şifre sözlüğü
USER_CREDENTIALS = {
    "alibaranariban": "smart",
    "alioguz": "smart",
    "neciphayran": "smart",
    "sertacaltinok": "smart",
    "zeynepegeuysal": "smart",
    "ahmetcangunaydin": "smart",
    "busraunlu": "smart",
    "hakanyavas": "smart",
    "irmaksargin": "smart",
    "simgecinaraygun": "smart"
}

def check_credentials(username, password):
    return USER_CREDENTIALS.get(username) == password
