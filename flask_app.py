import os
import io
import uuid
import json
import base64
import smtplib
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
from flask import Flask, render_template, request, send_file, jsonify
from xhtml2pdf import pisa
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from email.header import Header
from urllib.parse import quote
from PIL import Image

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- [이메일 설정] ---
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
DEFAULT_EMAIL = os.environ.get("DEFAULT_EMAIL", "ai-rnd@ysfc.co.kr")

PROJECT_INFO = {
    "건식과제": {
        "full_name": "5KPM급 건식전극 연속식 믹싱 장비 및 공정 개발",
        "period": "2025.06.01 ~ 2026.03.31"
    },
    "상생과제": {
        "full_name": "연속가동신뢰성 확보 두께편차 ±3%이하 이차전지 건식전극 제조공정 장비 개발",
        "period": "2026.01.01 ~ 2026.12.31"
    }
}

# --- [검수확인서 번호 생성] ---
COUNTER_FILE = os.path.join(BASE_DIR, "doc_counter.json")

def generate_doc_number():
    today = datetime.now().strftime("%Y-%m%d")
    data = {}
    if os.path.exists(COUNTER_FILE):
        try:
            with open(COUNTER_FILE, "r") as f:
                data = json.load(f)
        except:
            data = {}
    count = data.get(today, 0) + 1
    data[today] = count
    with open(COUNTER_FILE, "w") as f:
        json.dump(data, f)
    return f"{today}-{count:03d}"

def send_pdf_email(file_name, pdf_content, target_email):
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_USER
        msg['To'] = target_email
        msg['Subject'] = Header(f"[{file_name}] 검수확인서 자동 발송", 'utf-8').encode()

        body = f"안녕하세요. 시스템에서 생성된 {file_name} 파일을 보내드립니다."
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        part = MIMEBase('application', 'octet-stream')
        part.set_payload(pdf_content)
        encoders.encode_base64(part)

        encoded_filename = Header(file_name, 'utf-8').encode()
        part.add_header('Content-Disposition', 'attachment', filename=encoded_filename)
        msg.attach(part)

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, target_email, msg.as_string())
        server.quit()
        return True, ""
    except Exception as e:
        print(f"Mail Error: {e}")
        return False, str(e)

@app.route('/')
def index():
    return render_template('index.html', projects=PROJECT_INFO.keys(), default_email=DEFAULT_EMAIL)

def build_pdf(form, is_preview=False):
    """PDF 생성 공통 로직. (is_preview=True면 문서번호 미부여)"""
    temp_files = []
    try:
        req_id = uuid.uuid4().hex[:8]
        project_key = form.get('project', '')
        info = PROJECT_INFO.get(project_key, {"full_name": "", "period": ""})
        product = form.get('product', '')
        name = form.get('name', '')
        customer = form.get('customer', '')
        date = form.get('date', '')

        photo_paths = []
        MAX_WIDTH = 480
        for i in range(1, 5):
            photo_data = form.get(f'photo{i}_data')
            if photo_data and ',' in photo_data:
                save_path = os.path.join(BASE_DIR, f"temp_photo_{req_id}_{i}.jpg")
                _, encoded = photo_data.split(",", 1)
                img_bytes = base64.b64decode(encoded)
                img = Image.open(io.BytesIO(img_bytes))
                img = img.convert('RGB')
                if img.width > MAX_WIDTH:
                    ratio = MAX_WIDTH / img.width
                    img = img.resize((MAX_WIDTH, int(img.height * ratio)), Image.LANCZOS)
                img.save(save_path, 'JPEG', quality=90)
                photo_paths.append(save_path)
                temp_files.append(save_path)

        sig_data = form.get('signature_data', '')
        sig_path = ""
        if sig_data and ',' in sig_data:
            sig_path = os.path.join(BASE_DIR, f"temp_sig_{req_id}.png")
            _, encoded = sig_data.split(",", 1)
            with open(sig_path, "wb") as f:
                f.write(base64.b64decode(encoded))
            temp_files.append(sig_path)

        doc_number = "(미리보기)" if is_preview else generate_doc_number()

        context = {
            'doc_number': doc_number,
            'project_name': info['full_name'], 'period': info['period'],
            'customer': customer, 'product': product, 'name': name, 'date': date,
            'photo_paths': photo_paths, 'sig_path': sig_path,
            'font_path': os.path.join(BASE_DIR, "Pretendard-Regular.ttf")
        }

        rendered_html = render_template('report.html', **context)
        pdf_io = io.BytesIO()
        pisa.CreatePDF(src=rendered_html.encode("UTF-8"), dest=pdf_io, encoding='UTF-8')
        pdf_bytes = pdf_io.getvalue()

        safe_product = product.replace('/', '_').replace('\\', '_').replace(':', '_')
        file_name = f"검수확인서_{safe_product}_{name}.pdf"

        return pdf_bytes, file_name, None
    except Exception as e:
        import traceback
        traceback.print_exc()
        return None, None, f"{type(e).__name__}: {e}"
    finally:
        for f in temp_files:
            try:
                os.remove(f)
            except OSError:
                pass

@app.route('/preview', methods=['POST'])
def preview():
    pdf_bytes, file_name, error = build_pdf(request.form, is_preview=True)
    if error:
        return error, 500
    pdf_io = io.BytesIO(pdf_bytes)
    return send_file(pdf_io, mimetype='application/pdf', download_name=file_name)

@app.route('/generate', methods=['POST'])
def generate():
    pdf_bytes, file_name, error = build_pdf(request.form, is_preview=False)
    if error:
        return jsonify({"success": False, "error": error}), 500

    target_email = request.form.get('target_email', DEFAULT_EMAIL).strip()
    if not target_email:
        target_email = DEFAULT_EMAIL

    mail_ok, mail_error = send_pdf_email(file_name, pdf_bytes, target_email)

    # PDF를 base64로 인코딩하여 JSON 응답에 포함
    pdf_b64 = base64.b64encode(pdf_bytes).decode('utf-8')
    return jsonify({
        "success": True,
        "mail_ok": mail_ok,
        "mail_error": mail_error,
        "target_email": target_email,
        "file_name": file_name,
        "pdf_data": pdf_b64
    })

if __name__ == '__main__':
    app.run(debug=True)
