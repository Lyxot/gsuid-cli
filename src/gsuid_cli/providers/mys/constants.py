from __future__ import annotations

from datetime import timedelta, timezone

PROVIDER = "mys"
RECORD_BASE_CN = "https://api-takumi-record.mihoyo.com"
GS_BASE_CN = "https://api-takumi.mihoyo.com"
HK4_API_BASE_CN = "https://hk4e-api.mihoyo.com"
PASSPORT_BASE_CN = "https://passport-api.mihoyo.com"
HK4_SDK_BASE_CN = "https://hk4e-sdk.mihoyo.com"
NEW_BBS_BASE_CN = "https://bbs-api.miyoushe.com"
GET_FP_URL = "https://public-data-api.mihoyo.com/device-fp/api/getFp"
GACHA_LOG_URL = "https://public-operation-hk4e.mihoyo.com/gacha_info/api/getGachaLog"
INDEX_PATH = "/game_record/app/genshin/api/index"
CARD_PATH = "/game_record/card/wapi/getGameRecordCard"
DAILY_NOTE_PATH = "/game_record/app/genshin/api/dailyNote"
ABYSS_PATH = "/game_record/app/genshin/api/spiralAbyss"
ROLE_COMBAT_PATH = "/game_record/app/genshin/api/role_combat"
HARD_CHALLENGE_PATH = "/game_record/app/genshin/api/hard_challenge"
ACHIEVEMENT_PATH = "/game_record/app/genshin/api/achievement"
GCG_BASIC_PATH = "/game_record/app/genshin/api/gcg/basicInfo"
GCG_DECK_PATH = "/game_record/app/genshin/api/gcg/deckList"
CHARACTER_LIST_PATH = "/game_record/app/genshin/api/character/list"
CHARACTER_DETAIL_PATH = "/game_record/app/genshin/api/character/detail"
ACT_CALENDAR_PATH = "/game_record/app/genshin/api/act_calendar"
MONTHLY_AWARD_PATH = "/event/ys_ledger/monthInfo"
SIGN_INFO_PATH = "/event/luna/info"
SIGN_PATH = "/event/luna/sign"
CALCULATOR_BATCH_COMPUTE_PATH = "/event/e20200928calculate/v3/batch_compute"
HK4E_LOGIN_PATH = "/common/badge/v1/login/account"
REGISTER_TIME_PATH = "/event/e20220928anniversary/game_data"
CREATE_QRCODE_PATH = "/hk4e_cn/combo/panda/qrcode/fetch"
CHECK_QRCODE_PATH = "/hk4e_cn/combo/panda/qrcode/query"
GET_STOKEN_BY_GAME_TOKEN_PATH = "/account/ma-cn-session/app/getTokenByGameToken"
GET_COOKIE_TOKEN_BY_STOKEN_PATH = "/account/auth/api/getCookieAccountInfoBySToken"
GET_AUTHKEY_PATH = "/binding/api/genAuthKey"
DEVICE_LOGIN_PATH = "/apihub/api/deviceLogin"
SAVE_DEVICE_PATH = "/apihub/api/saveDevice"
APP_VERSION = "2.102.1"
RECORD_SALT = "xV8v4Qu54lUKrEYFZkJhB8cuOh9Asafs"
WEB_SALT = "yBh10ikxtLPoIhgwgPZSv5dmfaOTSJ6a"
PASSPORT_SALT = "JwYDpKvLj6MrMqqYU6jTKF17KNO2PXoS"
SIGN_ACT_ID = "e202311201442471"
USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 13; PHK110 Build/SKQ1.221119.001; wv)"
    "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/"
    f"126.0.6478.133 Mobile Safari/537.36 miHoYoBBS/{APP_VERSION}"
)

SERVER_BY_UID_PREFIX = {
    "1": "cn_gf01",
    "2": "cn_gf01",
    "5": "cn_qd01",
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
