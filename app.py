import streamlit as st
import os
import shutil
import pandas as pd
from datetime import datetime

import openai
from openai import OpenAI
openai.api_key = st.secrets["OPENAI_API_KEY"]
model_name = "gpt-4o-mini"

# 기본 폴더 경로
BASE_DIR = "dir"

# 최초 실행 시 1번만 폴더 생성 (세션 상태 유지)
if "foldername" not in st.session_state:
    current_time = datetime.now()
    st.session_state.foldername = current_time.isoformat().replace(":", "_")

UPLOAD_FOLDER = os.path.join(BASE_DIR, st.session_state.foldername)

# 폴더 생성 (최초 1회만 실행됨)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def save_uploaded_file(directory, file):
    file_path = os.path.join(directory, file.name)
    
    if file.name.endswith(".txt"):
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(file.getvalue().decode("utf-8"))
    else:
        with open(file_path, "wb") as f:
            f.write(file.getbuffer())

    return st.success(f"파일 업로드 성공! ({file.name})")

# 📂 폴더 삭제 함수
def delete_folder(directory):
    if os.path.exists(directory):
        shutil.rmtree(directory)
        os.makedirs(directory, exist_ok=True)  # 빈 폴더 다시 생성
        return st.success("📂 업로드된 파일이 모두 삭제되었습니다.")

# 📂 업로드된 파일 목록 조회 함수
def get_uploaded_files(directory):
    if os.path.exists(directory):
        return os.listdir(directory)
    return []

# 기본 형식
def main():
    st.title("회의록 작성 시스템")

    # 📂 파일 업로드 섹션
    st.header("1️⃣ 파일 업로드")
    uploaded_file = st.file_uploader("파일을 업로드하세요 (PDF, DOCX, TXT)", type=["pdf", "docx", "txt"])

    if uploaded_file is not None:
        save_uploaded_file(UPLOAD_FOLDER, uploaded_file)

    # 📂 폴더 삭제 버튼 추가
    if st.button("📂 폴더 삭제"):
        delete_folder(UPLOAD_FOLDER)

    st.markdown("---")

    # 📋 업로드된 파일 목록 섹션
    st.header("2️⃣ 업로드된 파일 목록")
    files = get_uploaded_files(UPLOAD_FOLDER)

    if len(files) == 0:
        st.warning("현재 업로드된 파일이 없습니다.")
    else:
        st.success(f"현재 저장된 파일 수: {len(files)}개")
        file_df = pd.DataFrame({"파일명": files}, index=range(1, len(files) + 1))
        st.table(file_df)

    st.markdown("---")

    # 📝 회의록 작성 섹션
    st.header("3️⃣ 회의록 작성")
    
    meeting_name = st.text_input("회의 이름을 입력하세요:", "")
    meeting_topic = st.text_input("회의 주제를 입력하세요:", "")
    
    start_button = st.button("회의록 작성 시작")

    output_placeholder = st.empty()  # GPT 결과 출력을 위한 placeholder

    if start_button:
        if not meeting_name.strip():
            st.warning("⚠️ 회의 이름을 입력하세요!")
            return
        
        meeting_name = meeting_name.strip()
        
        if not meeting_topic.strip():
            st.warning("⚠️ 회의 주제를 입력하세요!")
            return

        meeting_topic = meeting_topic.strip()
        
        log_text = f"🔹 '{meeting_topic}' 주제에 대한 회의록 작성을 시작합니다...  \n"
        output_placeholder.text_area("📜 진행 상황 및 결과", log_text, height=300)

        if not files:
            log_text += "⚠️ 업로드된 파일이 없습니다. 먼저 파일을 업로드하세요.  \n"
            output_placeholder.text_area("📜 진행 상황 및 결과", log_text, height=300)
            return

        client = OpenAI()
        user1 = client.beta.threads.create()

        vector_store = client.beta.vector_stores.create(name="회의내용",
          expires_after={
            "anchor": "last_active_at",
            "days": 1
          })
        file_paths = [os.path.join(UPLOAD_FOLDER, filename) for filename in os.listdir(UPLOAD_FOLDER)]
        file_streams = [open(path, "rb") for path in file_paths]
        
        file_batch = client.beta.vector_stores.file_batches.upload_and_poll(
          vector_store_id=vector_store.id, files=file_streams
        )
        
        log_text += f"📄 총 {len(files)}개의 파일을 분석 중...  \n"
        output_placeholder.text_area("📜 진행 상황 및 결과", log_text, height=300)

        assistant = client.beta.assistants.create(
          instructions=f"""회의록을 작성해주는 어시스턴트 봇이다.
          """,
          model=model_name,
          tools=[{"type": "file_search"}]
        )
        
        assistant = client.beta.assistants.update(
          assistant_id=assistant.id,
          tool_resources={"file_search": {"vector_store_ids": [vector_store.id]}},
        )

        run = client.beta.threads.runs.create_and_poll(
          thread_id=user1.id,
          assistant_id=assistant.id,
          instructions=f"""다음은 회의록 스크립트이다. 
          위 내용을 참고한 {meeting_topic}이 주제이고 제목이 {meeting_name}인 회의록을 한글로 자세하게 작성해주세요.
          출처에 대한 내용은 달지 말아주세요.
          - 신뢰할 수 없는 정보는 포함하지 마세요.  
          - 모호하거나 확인되지 않은 내용은 절대 생성하지 마세요.  
          다음 규칙, 응답 구조, 응답 예시에 따라 작성해주세요.
                ■ 규칙:
                * 필수 입력 값:
                - "회의 내용" (필수)
                * 선택 입력 값:
                - "날짜", "장소", "회의 매니저", "회의 기록자", "회의 참여자", "참조" 항목 누락 시 AI가 사용자에게 부족한 정보가 있음을 알리고 추가 입력을 요청할 수 있음: "XXX 항목이 없습니다. 입력해주세요."
                - 그럼에도 불구하고 "날짜", "장소", "회의 매니저", "회의 기록자", "회의 참여자", "참조" 항목이 명시적으로 입력되지 않은 경우, AI가 임의로 값을 채우지 말고 해당 정보가 없는 경우, 빈 칸(미입력 상태)으로 두고 유지해주세요.
                * 불필요한 잡담 제거 및 MECE 기반 정리
                * 랩업(Wrap-up) 자동 생성:
                - 결정 사항 / 액션 아이템 / Next Step 자동 추출
                * 기본 Markdown 출력
                ■ 응답 구조

                # 회의록 제목 (회의록 내용 분석 후 회의록 제목 기재)
                <table style="width:80%; border-collapse: collapse;" border="1">
                    <colgroup>
                        <col style="width: 30%;">
                        <col style="width: 70%;">
                    </colgroup">
                    <tr>
                        <th><strong>날짜</strong></th>
                        <td>YYYY-MM-DD</td>
                    </tr>
                    <tr>
                        <th><strong>장소</strong></th>
                        <td>(회의 장소)</td>
                    </tr>
                    <tr>
                        <th><strong>회의 매니저</strong></th>
                        <td>@멘션</td>
                    </tr>
                    <tr>
                        <th><strong>회의 기록자</strong></th>
                        <td>@멘션</td>
                    </tr>
                    <tr>
                        <th><strong>회의 참여자</strong></th>
                        <td>@멘션</td>
                    </tr>
                    <tr>
                        <th><strong>참조</strong></th>
                        <td>@멘션</td>
                    </tr>
                </table>
                
                ## **아젠다**
                *   (당일 회의 핵심 아젠다를 두괄식으로 기재)
                *   *
                ## 회의 내용
                ### 1. 제목
                *   (정리된 회의 내용)
                ### 2. 제목
                *   (정리된 회의 내용)
                ### 3. 제목
                *   (정리된 회의 내용)
                ## 랩업
                *   (회의 후 결정 사항, 액션 아이템, Next Step 등 정리)
                *   **Action Items**
                    - (액션 아이템)
                *   **결정 사항**
                    - (결정 사항)
                    
          """
        )
        
        messages = client.beta.threads.messages.list(
          thread_id = user1.id
        )

        result = messages.data[0].content[0].text.value

        # GPT 결과 업데이트
        log_text += f"🔹 OpenAI {model_name} 결과:  \n{result}  \n"
        
        output_placeholder.markdown(log_text);
        
        # GPT 결과를 파일로 저장
        output_file_path = os.path.join("./", f"회의록_{meeting_name}.txt")
        with open(output_file_path, "w", encoding="utf-8") as f:
            f.write(str(result))  # ✅ Output을 문자열로 변환하여 저장

        log_text += f"  \n✅ '{meeting_topic}' 주제에 대한 회의록 작성을 완료하였습니다!  \n"
        
        output_placeholder.markdown(log_text, unsafe_allow_html=True);

        # 파일 및 vectorstore 삭제
        all_files = list(client.beta.vector_stores.files.list(vector_store_id = vector_store.id))
        for file in all_files:
            client.files.delete(file.id)
        client.beta.vector_stores.delete(vector_store.id)

        # 파일 다운로드 버튼 제공
        with open(output_file_path, "rb") as file:
            st.download_button("📥 회의록 다운로드", file, file_name=f"회의록_{meeting_name}.txt")

if __name__ == "__main__":
    main()
