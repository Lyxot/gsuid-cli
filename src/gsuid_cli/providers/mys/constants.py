from __future__ import annotations

from datetime import timedelta, timezone

PROVIDER = "mys"
RECORD_BASE_CN = "https://api-takumi-record.mihoyo.com"
GS_BASE_CN = "https://api-takumi.mihoyo.com"
HK4_API_BASE_CN = "https://hk4e-api.mihoyo.com"
RECORD_BASE_OS = "https://bbs-api-os.hoyolab.com"
GS_BASE_OS = "https://api-os-takumi.mihoyo.com"
HK4_API_BASE_OS = "https://hk4e-api-os.hoyoverse.com"
SIGN_BASE_OS = "https://sg-hk4e-api.hoyolab.com"
ACT_BASE_OS = "https://sg-hk4e-api.hoyoverse.com"
PASSPORT_BASE_CN = "https://passport-api.mihoyo.com"
HK4_SDK_BASE_CN = "https://hk4e-sdk.mihoyo.com"
NEW_BBS_BASE_CN = "https://bbs-api.miyoushe.com"
BBS_BASE_CN = "https://bbs-api.mihoyo.com"
GET_FP_URL = "https://public-data-api.mihoyo.com/device-fp/api/getFp"
GACHA_LOG_URL = "https://public-operation-hk4e.mihoyo.com/gacha_info/api/getGachaLog"
GACHA_LOG_URL_OS = f"{HK4_API_BASE_OS}/gacha_info/api/getGachaLog"
INDEX_PATH = "/game_record/app/genshin/api/index"
INDEX_PATH_OS = "/game_record/genshin/api/index"
CARD_PATH = "/game_record/card/wapi/getGameRecordCard"
DAILY_NOTE_PATH = "/game_record/app/genshin/api/dailyNote"
DAILY_NOTE_PATH_OS = "/game_record/genshin/api/dailyNote"
ABYSS_PATH = "/game_record/app/genshin/api/spiralAbyss"
ABYSS_PATH_OS = "/game_record/genshin/api/spiralAbyss"
ROLE_COMBAT_PATH = "/game_record/app/genshin/api/role_combat"
HARD_CHALLENGE_PATH = "/game_record/app/genshin/api/hard_challenge"
ACHIEVEMENT_PATH = "/game_record/app/genshin/api/achievement"
GCG_BASIC_PATH = "/game_record/app/genshin/api/gcg/basicInfo"
GCG_BASIC_PATH_OS = "/game_record/genshin/api/gcg/basicInfo"
GCG_DECK_PATH = "/game_record/app/genshin/api/gcg/deckList"
CHARACTER_LIST_PATH = "/game_record/app/genshin/api/character/list"
CHARACTER_LIST_PATH_OS = "/game_record/genshin/api/character"
CHARACTER_DETAIL_PATH = "/game_record/app/genshin/api/character/detail"
ACT_CALENDAR_PATH = "/game_record/app/genshin/api/act_calendar"
MONTHLY_AWARD_PATH = "/event/ys_ledger/monthInfo"
MONTHLY_AWARD_PATH_OS = "/event/ysledgeros/month_info"
SIGN_INFO_PATH = "/event/luna/info"
SIGN_INFO_PATH_OS = "/event/sol/info"
SIGN_PATH = "/event/luna/sign"
SIGN_PATH_OS = "/event/sol/sign"
CALCULATOR_BATCH_COMPUTE_PATH = "/event/e20200928calculate/v3/batch_compute"
HK4E_LOGIN_PATH = "/common/badge/v1/login/account"
REGISTER_TIME_PATH = "/event/e20220928anniversary/game_data"
CREATE_QRCODE_PATH = "/hk4e_cn/combo/panda/qrcode/fetch"
CHECK_QRCODE_PATH = "/hk4e_cn/combo/panda/qrcode/query"
CREATE_QRCODE_HYP_PATH = "/account/ma-cn-passport/app/createQRLogin"
CHECK_QRCODE_HYP_PATH = "/account/ma-cn-passport/app/queryQRLoginStatus"
GET_STOKEN_BY_GAME_TOKEN_PATH = "/account/ma-cn-session/app/getTokenByGameToken"
GET_COOKIE_TOKEN_BY_STOKEN_PATH = "/account/auth/api/getCookieAccountInfoBySToken"
GET_AUTHKEY_PATH = "/binding/api/genAuthKey"
DEVICE_LOGIN_PATH = "/apihub/api/deviceLogin"
SAVE_DEVICE_PATH = "/apihub/api/saveDevice"
BBS_TASKS_LIST_PATH = "/apihub/sapi/getUserMissionsState"
BBS_SIGN_PATH = "/apihub/app/api/signIn"
BBS_LIST_PATH = "/post/api/getForumPostList"
BBS_DETAIL_PATH = "/post/api/getPostFull"
BBS_SHARE_PATH = "/apihub/api/getShareConf"
BBS_LIKE_PATH = "/apihub/sapi/upvotePost"
APP_VERSION = "2.102.1"
RECORD_SALT = "xV8v4Qu54lUKrEYFZkJhB8cuOh9Asafs"
WEB_SALT = "yBh10ikxtLPoIhgwgPZSv5dmfaOTSJ6a"
BBS_SALT = "lX8m5VO5at5JG7hR8hzqFwzyL5aB1tYo"
BBS_SIGN_SALT = "t0qEgfub6cvueAPgR5m9aQWWVciEer7v"
PASSPORT_SALT = "JwYDpKvLj6MrMqqYU6jTKF17KNO2PXoS"
SIGN_ACT_ID = "e202311201442471"
SIGN_ACT_ID_OS = "e202102251931481"
USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 13; PHK110 Build/SKQ1.221119.001; wv)"
    "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/"
    f"126.0.6478.133 Mobile Safari/537.36 miHoYoBBS/{APP_VERSION}"
)

SERVER_BY_UID_PREFIX = {
    "1": "cn_gf01",
    "2": "cn_gf01",
    "5": "cn_qd01",
    "6": "os_usa",
    "7": "os_euro",
    "8": "os_asia",
    "9": "os_cht",
}
ELEMENT_ID_BY_NAME = {
    "Pyro": 1,
    "Anemo": 2,
    "Geo": 3,
    "Dendro": 4,
    "Electro": 5,
    "Hydro": 6,
    "Cryo": 7,
}
CN_TIMEZONE = timezone(timedelta(hours=8))
