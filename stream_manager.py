"""TikTok stream creation + end (reused from snake game)."""
import json
import logging
import os
import random
import time
import requests

log = logging.getLogger("stream")


def load_cookies() -> dict:
    path = os.environ.get("COOKIES_PATH", "/app/cookies.json")
    with open(path) as f:
        cookies_list = json.load(f)
    return {c["name"]: c["value"] for c in cookies_list}


def get_server_url(session: requests.Session) -> str:
    url = (
        "https://tnc16-platform-useast1a.tiktokv.com/get_domains/v4/?"
        "aid=8311&ttwebview_version=1130022001&device_platform=win"
    )
    try:
        resp = session.get(url, timeout=15).json()
        for data in resp.get("data", {}).get("ttnet_dispatch_actions", []):
            if "param" in data and "strategy_info" in data["param"]:
                si = data["param"]["strategy_info"]
                if "webcast-normal.tiktokv.com" in si:
                    server = si["webcast-normal.tiktokv.com"]
                    for d2 in resp["data"]["ttnet_dispatch_actions"]:
                        if ("param" in d2 and "strategy_info" in d2["param"]
                                and server in d2["param"]["strategy_info"]):
                            server = d2["param"]["strategy_info"][server]
                    return f"https://{server}/"
    except Exception as e:
        log.warning(f"Server URL lookup failed: {e}")
    return "https://webcast-normal.tiktokv.com/"


def _end_existing_stream(session: requests.Session):
    """End any lingering live stream."""
    try:
        base = get_server_url(session)
        params = {"aid": "1233", "app_name": "musical_ly", "device_platform": "android"}
        resp = session.post(base + "webcast/room/finish_abnormal/", params=params, timeout=15)
        result = resp.json()
        if result.get("status_code") == 0:
            log.info("Ended previous stream ✓")
            time.sleep(2)
        else:
            log.debug(f"No active stream to end: {result.get('status_code')}")
    except Exception as e:
        log.debug(f"End stream check: {e}")


def create_stream(title: str = "🎮 Live Stream 24/7") -> dict | None:
    cookies = load_cookies()
    s = requests.Session()
    s.cookies.update(cookies)

    _end_existing_stream(s)

    base_url = get_server_url(s)
    log.info(f"Server URL: {base_url}")

    device_id = "".join([str(random.randint(0, 9)) for _ in range(19)])
    iid = "".join([str(random.randint(0, 9)) for _ in range(19)])
    openudid = "".join([random.choice("0123456789abcdef") for _ in range(16)])

    s.headers = {
        "user-agent": (
            "com.zhiliaoapp.musically/2023508030 (Linux; U; Android 14; en_US; "
            "M2102J20SG; Build/AP2A.240905.003; Cronet/TTNetVersion:f58efab5 "
            "2024-06-13 QuicVersion:5d23606e 2024-05-23)"
        ),
    }

    params = {
        "aid": "1233", "app_name": "musical_ly", "channel": "googleplay",
        "device_platform": "android", "iid": iid, "device_id": device_id,
        "openudid": openudid, "os": "android", "ssmix": "a",
        "_rticket": str(int(time.time() * 1000)),
        "version_code": "370104", "version_name": "37.1.4",
        "manifest_version_code": "2024701040", "update_version_code": "2024701040",
        "ab_version": "37.1.4", "resolution": "1080*2309", "dpi": "410",
        "device_type": "M2102J20SG", "device_brand": "POCO",
        "language": "en", "os_api": "34", "os_version": "14",
        "ac": "wifi", "is_pad": "0", "current_region": "DZ",
        "app_type": "normal", "sys_region": "US",
        "timezone_name": "Africa/Algiers", "residence": "DZ",
        "app_language": "en", "carrier_region": "DZ",
        "region": "US", "ts": str(int(time.time())),
        "webcast_sdk_version": "3590", "webcast_language": "en",
    }

    data = {
        "hashtag_id": "1659889196", "title": title,
        "hold_living_room": "1", "chat_sub_only_auth": "2",
        "live_sub_only": "0", "chat_l_2": "1",
        "create_source": "0", "chat_auth": "1",
        "gift_auth": "1", "gen_replay": "false",
        "game_tag_id": "0", "age_restricted": "0",
    }

    try:
        resp = s.post(base_url + "webcast/room/create/", params=params, data=data, timeout=30)
        result = resp.json()

        if "data" in result and "stream_url" in result.get("data", {}):
            rtmp_url = result["data"]["stream_url"]["rtmp_push_url"]
            idx = rtmp_url.rfind("/")
            share_url = result["data"].get("share_url", "")
            log.info(f"Stream created! Share: {share_url}")
            return {
                "base_url": rtmp_url[:idx],
                "key": rtmp_url[idx + 1:],
                "rtmp_url": rtmp_url,
                "share_url": share_url,
            }
        else:
            status = result.get("status_code")
            msg = result.get("data", {}).get("prompts", result.get("data", {}).get("message", ""))
            log.error(f"Stream creation failed (status={status}): {msg}")
            if status == 30005:
                log.info("Already live — ending and retrying…")
                _end_existing_stream(s)
                time.sleep(3)
                try:
                    resp2 = s.post(base_url + "webcast/room/create/", params=params, data=data, timeout=30)
                    r2 = resp2.json()
                    if "stream_url" in r2.get("data", {}):
                        rtmp_url = r2["data"]["stream_url"]["rtmp_push_url"]
                        idx = rtmp_url.rfind("/")
                        share_url = r2["data"].get("share_url", "")
                        log.info(f"Stream created (retry)! Share: {share_url}")
                        return {
                            "base_url": rtmp_url[:idx],
                            "key": rtmp_url[idx + 1:],
                            "rtmp_url": rtmp_url,
                            "share_url": share_url,
                        }
                except Exception as e2:
                    log.error(f"Retry also failed: {e2}")
            return None
    except Exception as e:
        log.error(f"Error creating stream: {e}")
        return None


def end_stream():
    cookies = load_cookies()
    s = requests.Session()
    s.cookies.update(cookies)
    s.headers = {
        "user-agent": "com.zhiliaoapp.musically/2023508030 (Linux; U; Android 14; en_US)",
    }
    base_url = get_server_url(s)
    params = {"aid": "1233", "app_name": "musical_ly", "channel": "googleplay",
              "device_platform": "android"}
    try:
        resp = s.post(base_url + "webcast/room/finish_abnormal/", params=params, timeout=15)
        log.info(f"Stream ended: {resp.json()}")
    except Exception as e:
        log.warning(f"End stream error: {e}")
