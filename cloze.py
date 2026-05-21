import streamlit as st
from docx import Document
import nltk
from nltk import pos_tag, word_tokenize
import random
import re

# ---------- NLTK data ----------
try:
    nltk.data.find("tokenizers/punkt")
except LookupError:
    nltk.download("punkt", quiet=True)

try:
    nltk.data.find("tokenizers/punkt_tab")
except LookupError:
    nltk.download("punkt_tab", quiet=True)

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
    "전치사": {"IN"},
    "접속사": {"CC"},
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

        if re.fullmatch(r"[^\w\s]", t):
            out += t
        else:
            out += " " + t
    return out


# ---------- 문제 생성용 함수 ----------
def generate_questions_from_docx(file_like, pos_choice, blank_count):
    src = Document(file_like)

    question_paragraphs = []
    answer_map = {}
    next_blank_num = 1

    # 전체 후보 저장
    all_candidates = []

    paragraph_data = []

    for para_idx, para in enumerate(src.paragraphs):
        orig_text = para.text.strip()

        if not orig_text:
            paragraph_data.append(None)
            question_paragraphs.append("")
            continue

        tokens = tokenize_preserve_spacing(orig_text)

        try:
            tagged = pos_tag(tokens)
        except Exception:
            tagged = [(t, "NN") for t in tokens]

        candidate_indices = []

        for i, (tok, tg) in enumerate(tagged):
            if is_candidate_token(tok):

                if pos_choice == "전체":
                    candidate_indices.append(i)

                else:
                    if tg in POS_GROUPS.get(pos_choice, set()):
                        candidate_indices.append(i)

        if not candidate_indices:
            candidate_indices = [
                i for i, (tok, tg) in enumerate(tagged)
                if is_candidate_token(tok)
            ]

        paragraph_data.append({
            "tokens": tokens,
            "candidate_indices": candidate_indices
        })

        for idx in candidate_indices:
            all_candidates.append((para_idx, idx))

        question_paragraphs.append("")

    # 실제 빈칸 개수 제한
    blank_count = min(blank_count, len(all_candidates))

    # 랜덤 선택
    chosen_candidates = random.sample(all_candidates, blank_count) if blank_count > 0 else []

    chosen_set = set(chosen_candidates)

    # 문단 재조립
    for para_idx, pdata in enumerate(paragraph_data):

        if pdata is None:
            continue

        tokens = list(pdata["tokens"])

        for idx in pdata["candidate_indices"]:

            if (para_idx, idx) in chosen_set:

                original_word = tokens[idx]
                underline = "_" * max(3, len(original_word))

                tokens[idx] = f"({next_blank_num}){underline}"

                answer_map[next_blank_num] = original_word
                next_blank_num += 1

        question_paragraphs[para_idx] = assemble_tokens(tokens)

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

        results.append({
            "num": num,
            "correct": correct,
            "user": user_ans,
            "is_correct": is_correct,
        })

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

# 상단 정보란
col_major, col_name = st.columns(2)

with col_major:
    major_name = st.text_input(
        "전공",
        value="",
        placeholder="예: 영어교육과"
    )

with col_name:
    student_name = st.text_input(
        "이름",
        value="",
        placeholder="예: 홍길동"
    )

st.markdown("---")

# 설정
pos_choice = st.selectbox(
    "빈칸으로 만들 품사 선택",
    ["전체", "동사", "명사", "형용사", "부사", "전치사", "접속사"]
)

blank_count = st.number_input(
    "빈칸 개수",
    min_value=1,
    max_value=200,
    value=10,
    step=1
)

uploaded_file = st.file_uploader(
    "Word(.docx) 파일 업로드",
    type=["docx"]
)

# 초기화
if st.button("🧹 초기화(새로 시작하기)"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# 문제 생성
if uploaded_file is not None:

    if st.button("📄 문제 만들기"):

        try:
            uploaded_file.seek(0)

            questions, answer_map = generate_questions_from_docx(
                uploaded_file,
                pos_choice,
                blank_count
            )

            st.session_state["questions"] = questions
            st.session_state["answer_map"] = answer_map

            st.success(
                "문제가 생성되었습니다. "
                "왼쪽 문제지를 보면서 아래에서 답을 입력하세요!"
            )

        except Exception as e:
            st.error("문제 생성 중 오류가 발생했습니다.")
            st.exception(e)

else:
    st.info("먼저 Word(.docx) 파일을 업로드하세요.")

st.markdown("---")

# --------- 사이드바 문제지 ---------
with st.sidebar:

    st.header("📝 문제지 (항상 표시)")

    if "questions" in st.session_state:

        questions = st.session_state["questions"]

        for para in questions:

            if para.strip() == "":
                st.write("")

            else:
                st.markdown(para)

    else:
        st.caption(
            "문제지가 여기에 표시됩니다. "
            "먼저 docx를 업로드하고 "
            "'문제 만들기'를 눌러 주세요."
        )

# --------- 답안 입력 ---------
if "answer_map" in st.session_state:

    answer_map = st.session_state["answer_map"]

    if len(answer_map) == 0:

        st.warning(
            "생성된 빈칸이 없습니다. "
            "다른 품사나 지문을 사용해 보세요."
        )

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

            score_pct = (
                (correct_count / total) * 100
                if total > 0 else 0.0
            )

            st.markdown("---")
            st.subheader("📊 채점 결과")

            st.write(
                f"총 {total}문항 중 "
                f"**{correct_count}개** 정답입니다."
            )

            st.write(
                f"점수: **{score_pct:.1f}점 / 100점**"
            )

            for r in results:

                num = r["num"]
                correct = r["correct"]
                user_ans = r["user"]

                if r["is_correct"]:

                    st.success(
                        f"{num}번: 정답! "
                        f"(입력: {user_ans})"
                    )

                else:

                    if user_ans.strip() == "":

                        st.error(
                            f"{num}번: 무응답. "
                            f"정답은 **{correct}** 입니다."
                        )

                    else:

                        st.error(
                            f"{num}번: 오답. "
                            f"입력: `{user_ans}`, "
                            f"정답: **{correct}**"
                        )

else:
    st.info("문제지를 먼저 생성해 주세요.")
