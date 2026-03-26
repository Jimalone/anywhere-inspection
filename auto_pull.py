"""
Git 자동 Pull 스크립트
- 30초마다 원격 저장소 변경 감지
- 변경이 있을 때만 git pull 실행
- 사내 서버에서 백그라운드로 실행: python auto_pull.py
"""
import subprocess
import time
import os
import sys

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
CHECK_INTERVAL = 30  # 초


def run_git(args):
    result = subprocess.run(
        ["git"] + args,
        cwd=REPO_DIR,
        capture_output=True,
        text=True
    )
    return result.stdout.strip(), result.returncode


def check_and_pull():
    # remote 최신 정보 가져오기 (실제 파일은 안 바뀜)
    _, rc = run_git(["fetch", "origin"])
    if rc != 0:
        print("[오류] git fetch 실패")
        return False

    # 로컬 HEAD vs 원격 HEAD 비교
    local, _ = run_git(["rev-parse", "HEAD"])
    remote, _ = run_git(["rev-parse", "origin/main"])

    if local == remote:
        return False

    # 변경 감지 → pull
    print(f"[변경 감지] local={local[:8]} → remote={remote[:8]}")
    out, rc = run_git(["pull", "origin", "main"])
    if rc == 0:
        print(f"[완료] git pull 성공: {out}")
        return True
    else:
        print(f"[오류] git pull 실패: {out}")
        return False


if __name__ == "__main__":
    print(f"[시작] {REPO_DIR}")
    print(f"[설정] {CHECK_INTERVAL}초 간격으로 변경 감지 중...")

    while True:
        try:
            check_and_pull()
        except Exception as e:
            print(f"[예외] {e}")
        time.sleep(CHECK_INTERVAL)
