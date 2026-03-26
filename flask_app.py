import os
import io
import uuid
import json
import base64
import smtplib
from datetime import datetime

from flask import Flask, render_template, request, send_file, jsonify
import tempfile
import xhtml2pdf.files as _xhtml2pdf_files

# --- [xhtml2pdf Windows file:/// URI 패치] ---
_orig_extract = _xhtml2pdf_files.LocalProtocolURI.extract_data
def _patched_extract(self):
    path = self.path
    if path and path.startswith('file:///'):
        local_path = path[8:]
        if os.path.isfile(local_path):
            self.uri = local_path
            with open(local_path, 'rb') as f:
                return f.read()
    elif path and len(path) > 2 and path[0] == '/' and path[2] == ':':
        local_path = path[1:]
        if os.path.isfile(local_path):
            self.uri = local_path
            with open(local_path, 'rb') as f:
                return f.read()
    return _orig_extract(self)
_xhtml2pdf_files.LocalProtocolURI.extract_data = _patched_extract

def _patched_get_named(self):
    data = self.get_data()
    tmp_file = tempfile.NamedTemporaryFile(suffix=self.suffix, delete=False)
    if data:
        tmp_file.write(data)
        tmp_file.flush()
        tmp_file.close()
        _xhtml2pdf_files.files_tmp.append(tmp_file)
    if self.path is None:
        self.path = tmp_file.name
    return tmp_file
_xhtml2pdf_files.BaseFile.get_named_tmp_file = _patched_get_named

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
SMTP_SERVER = "portal.ysfc.co.kr"
SMTP_PORT = 465
SMTP_USER = "ai-rnd@ysfc.co.kr"
SMTP_PASSWORD = "rd5925@@"
DEFAULT_EMAIL = "ai-rnd@ysfc.co.kr"

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
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
REPORT_LOG = os.path.join(REPORTS_DIR, "log.json")
os.makedirs(REPORTS_DIR, exist_ok=True)

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

        server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=10)
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
            'font_path': 'file:///' + os.path.join(BASE_DIR, "Pretendard-Regular.ttf").replace("\\", "/")
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

    # 발행 이력 저장
    save_report_log(request.form, file_name, pdf_bytes, mail_ok)

    pdf_b64 = base64.b64encode(pdf_bytes).decode('utf-8')
    return jsonify({
        "success": True,
        "mail_ok": mail_ok,
        "mail_error": mail_error,
        "target_email": target_email,
        "file_name": file_name,
        "pdf_data": pdf_b64
    })

def save_report_log(form, file_name, pdf_bytes, mail_ok):
    """발행된 검수확인서 PDF 저장 및 이력 기록"""
    try:
        # 문서번호 추출 (파일명에서 역산하지 않고 카운터에서 현재값 사용)
        with open(COUNTER_FILE, "r") as f:
            counter_data = json.load(f)
        today = datetime.now().strftime("%Y-%m%d")
        count = counter_data.get(today, 1)
        doc_number = f"{today}-{count:03d}"

        # PDF 파일 저장
        safe_doc = doc_number.replace('-', '_')
        pdf_path = os.path.join(REPORTS_DIR, f"{safe_doc}.pdf")
        with open(pdf_path, 'wb') as f:
            f.write(pdf_bytes)

        # 로그 기록
        entry = {
            "doc_number": doc_number,
            "date": form.get('date', ''),
            "project": form.get('project', ''),
            "product": form.get('product', ''),
            "customer": form.get('customer', ''),
            "name": form.get('name', ''),
            "email": form.get('target_email', DEFAULT_EMAIL),
            "mail_ok": mail_ok,
            "file_name": file_name,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        log_data = []
        if os.path.exists(REPORT_LOG):
            try:
                with open(REPORT_LOG, "r", encoding="utf-8") as f:
                    log_data = json.load(f)
            except:
                log_data = []
        log_data.append(entry)
        with open(REPORT_LOG, "w", encoding="utf-8") as f:
            json.dump(log_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Report log error: {e}")


@app.route('/admin')
def admin():
    log_data = []
    if os.path.exists(REPORT_LOG):
        try:
            with open(REPORT_LOG, "r", encoding="utf-8") as f:
                log_data = json.load(f)
        except:
            log_data = []
    log_data.reverse()
    return render_template('admin.html', reports=log_data)


@app.route('/admin/download/<doc_number>')
def admin_download(doc_number):
    safe_doc = doc_number.replace('-', '_')
    pdf_path = os.path.join(REPORTS_DIR, f"{safe_doc}.pdf")
    if not os.path.exists(pdf_path):
        return "파일을 찾을 수 없습니다.", 404
    return send_file(pdf_path, mimetype='application/pdf',
                     download_name=f"검수확인서_{doc_number}.pdf")

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
