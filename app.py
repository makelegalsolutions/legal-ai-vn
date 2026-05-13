import streamlit as st
import faiss
import pickle

from sentence_transformers import SentenceTransformer

st.set_page_config(
    page_title="AI giải đáp pháp luật VN? - Chính tôi!",
    layout="wide"
)

@st.cache_resource
def load_system():f

    index = faiss.read_index(
        "law_index.faiss"
    )

    with open(
        "metadata.pkl",
        "rb"
    ) as f:

        metadata = pickle.load(f)

    embedding_model = SentenceTransformer(
        "paraphrase-multilingual-MiniLM-L12-v2"
    )

    return index, metadata, embedding_model


index, metadata, embedding_model = load_system()


def search_law(
    query,
    top_k=5
):

    query_embedding = embedding_model.encode(
        [query],
        convert_to_numpy=True
    )

    distances, indices = index.search(
        query_embedding,
        top_k
    )

    results = []

    for idx in indices[0]:

        results.append(
            metadata[idx]
        )

    return results


st.title("⚖️ AI giải đáp pháp luật VN? - Chính tôi!")

st.caption(
    "What a wonderful world. Hệ thống demo, đang cập nhật thêm dữ liệu"
)

question = st.text_area(
    "Bạn cần gì cứ nói nhé, vô tư đi!Tôi không bao giờ nói nhiều, không bao giờ ép ăn và không bao giờ ép học."
)

if st.button("Trả lời"):

    docs = search_law(question)

    for d in docs:

        st.markdown("---")

        st.write(
            "Nguồn:",
            d["source"]
        )

        st.write(
            d["text"][:1500]
        )
