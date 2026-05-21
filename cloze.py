import streamlit as st
from docx import Document
import nltk
from nltk import pos_tag, word_tokenize
import random
import re

# ---------- NLTK data ----------
# 1) 문장/단어 토크나이저: punkt + punkt_tab
try:
    nltk.data.find("tokenizers/punkt")
except LookupError:
    nltk.download("punkt", quiet=True)

try:
    nltk.data.find("tokenizers/punkt_tab")
except LookupError:
    nltk.download("punkt_tab", quiet=True)

# 2) 품사 태거: 기존 이름 + 새로운 이름 모두 대비
try:
    nltk.data.find("taggers/averaged_perceptron_tagger")
except LookupError:
    try:
        nltk.data.find("taggers/averaged_perceptron_tagger_eng")
    except LookupError:
        nltk.download("averaged_perceptron_tagger", quiet=True)
        nltk.download("averaged_perceptron_tagger_eng", quiet=True)

# ---------- POS 그룹 ----------
POS_GROUPS = {
    "동사": {"VB", "VBD", "VBG", "VBN", "VBP", "VBZ"},
    "명사": {"NN", "NNS", "NNP", "NNPS"},
    "형용사": {"JJ", "JJR", "JJS"},
    "부사": {"RB", "RBR", "RBS"},
}

TOKEN_CANDIDATE_RE = re.compile(r"[A-Za-z0-9\uac00-\ud7a3]+")


def is_candidate_token(tok):
    return bool(TOKEN_CANDIDATE_RE.search(tok))


def tokenize_preserve_spacing(text):
    tokens = word_tokenize(text)
    return tokens


def assemble_tokens(tokens):
    out = ""
    for i, t in enumerate(tokens):
        if i == 0:
            out += t
            continue
        # 문장부호면 앞에 공백 없이
        if re.fullmatch(r"[^\w\s]", t):
            out += t
        else:
            out += " " + t
    return out


# ---------- 문제 생성용 함수 ----------
def generate_questions_from_docx(file_like, pos_choice, blank_ratio_fraction):
    src = Document(file_like)

    question_paragraphs = []  # 빈칸이 들어간 문단 문자열 리스트
    answer_map = {}           # {번호: 정답}
    next_blank_num = 1

    for para in src.paragraphs:
        orig_text = para.text.strip()
        if not orig_text:
            # 빈 줄도 유지
            question_paragraphs.append("")
            continue

        tokens = tokenize_preserve_spacing(orig_text)

        try:
            tagged = pos_tag(tokens)
        except Exception:
            # 태깅에 실패하면 전부 명사 취급
            tagged = [(t, "NN") for t in tokens]

        candidate_indices = []
        for i, (tok, tg) in enumerate(tagged):
            if is_candidate_token(tok):
                if pos_choice == "전체":
                    candidate_indices.append(i)
                else:
                    if tg in POS_GROUPS.get(pos_choice, set()):
                        candidate_indices.append(i)

        # 후보가 하나도 없으면 "단어 비슷한 것"은 다 후보로
        if not candidate_indices:
            candidate_indices = [
                i for i, (tok, tg) in enumerate(tagged) if is_candidate_token(tok)
            ]

        n_candidates = len(candidate_indices)
        n_blanks = max(0, int(round(n_candidates * blank_ratio_fraction)))
        n_blanks = min(n_blanks, n_candidates)

        chosen = []
        if n_blanks > 0 and n_candidates > 0:
            chosen = random.sample(candidate_indices, n_blanks)

        out_tokens = list(tokens)
        for idx in sorted(chosen):
            original_word = tokens[idx]
            underline = "_" * max(3, len(original_word))
            out_tokens[idx] = f"({next_blank_num}){underline}"
            answer_map[next_blank_num] = original_word
            next_blank_num += 1

        para_text = assemble_tokens(out_tokens)
        question_paragraphs.append(para_text)

    return question_paragraphs, answer_map


# ---------- 채점 함수 ----------
def grade_answers(answer_map):
    total = len(answer_map)
    if total == 0:
        return 0, 0, []

    correct_count = 0
    results = []

    for num in sorted(answer_map.keys()):
        correct = answer_map[num]
        user_key = f"answer_{num}"
        user_ans = st.session_state.get(user_key, "")
        user_norm = user_ans.strip().lower()
        correct_norm = correct.strip().lower()

        is_correct = (user_norm == correct_norm) and (user_norm != "")
        if is_correct:
            correct_count += 1

        results.append(
            {
                "num": num,
                "correct": correct,
                "user": user_ans,
                "is_correct": is_correct,
            }
        )

    return correct_count, total, results


# ---------------- Streamlit UI ----------------
st.set_page_config(page_title="Blank Test Web Quiz", layout="wide")

st.title("📘 Blank Test Web Quiz")
st.markdown(
    "업로드한 Word(.docx)에서 특정 품사만 선택하여 랜덤으로 빈칸을 생성하고, "
    "웹페이지에서 자동 채점까지 할 수 있습니다.\n\n"
    "**문제지 전체는 항상 왼쪽 사이드바에 고정**되어 있어서, "
    "스크롤을 내려도 지문을 계속 보면서 답을 입력할 수 있습니다."
)

# 상단 정보란 (반, 이름 등)
col_class, col_name = st.columns(2)
with col_class:
    class_name = st.text_input("반", value="", placeholder="예: 중3A반")
with col_name:
    student_name = st.text_input("이름", value="", placeholder="예: 홍길동")

st.markdown("---")

# 설정
pos_choice = st.selectbox("빈칸으로 만들 품사 선택", ["전체", "동사", "명사", "형용사", "부사"])
blank_pct = st.slider("빈칸 비율 (%)", min_value=5, max_value=80, value=20, step=5)

uploaded_file = st.file_uploader("Word(.docx) 파일 업로드", type=["docx"])

# 세션 상태 초기화 버튼
if st.button("🧹 초기화(새로 시작하기)"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# 문제 생성 버튼
if uploaded_file is not None:
    if st.button("📄 문제 만들기"):
        try:
            uploaded_file.seek(0)
            questions, answer_map = generate_questions_from_docx(
                uploaded_file, pos_choice, blank_pct / 100.0
            )
            st.session_state["questions"] = questions
            st.session_state["answer_map"] = answer_map
            st.success("문제가 생성되었습니다. 왼쪽 문제지를 보면서 아래에서 답을 입력하세요!")
        except Exception as e:
            st.error("문제 생성 중 오류가 발생했습니다.")
            st.exception(e)
else:
    st.info("먼저 Word(.docx) 파일을 업로드하세요.")

st.markdown("---")

# --------- 사이드바에 항상 문제지 표시 ---------
with st.sidebar:
    st.header("📝 문제지 (항상 표시)")
    if "questions" in st.session_state:
        questions = st.session_state["questions"]
        for para in questions:
            if para.strip() == "":
                st.write("")  # 빈 줄
            else:
                st.markdown(para)
    else:
        st.caption("문제지가 여기에 표시됩니다. 먼저 docx를 업로드하고 '문제 만들기'를 눌러 주세요.")

# --------- 메인 영역: 답안 입력 + 채점 ---------
if "answer_map" in st.session_state:
    answer_map = st.session_state["answer_map"]

    if len(answer_map) == 0:
        st.warning("생성된 빈칸이 없습니다. 빈칸 비율을 올리거나 다른 품사/지문을 사용해 보세요.")
    else:
        st.subheader("✏️ 답안 입력")

        for num in sorted(answer_map.keys()):
            st.text_input(
                label=f"{num}번",
                key=f"answer_{num}",
                placeholder=f"{num}번 정답을 입력하세요",
            )

        if st.button("✅ 채점하기"):
            correct_count, total, results = grade_answers(answer_map)
            score_pct = (correct_count / total) * 100 if total > 0 else 0.0

            st.markdown("---")
            st.subheader("📊 채점 결과")
            st.write(f"총 {total}문항 중 **{correct_count}개** 정답입니다.")
            st.write(f"점수: **{score_pct:.1f}점 / 100점**")

            for r in results:
                num = r["num"]
                correct = r["correct"]
                user_ans = r["user"]
                if r["is_correct"]:
                    st.success(f"{num}번: 정답! (입력: {user_ans})")
                else:
                    if user_ans.strip() == "":
                        st.error(f"{num}번: 무응답. 정답은 **{correct}** 입니다.")
                    else:
                        st.error(
                            f"{num}번: 오답. 입력: `{user_ans}`, 정답: **{correct}**"
                        )
else:
    st.info("문제지를 먼저 생성해 주세요.")
