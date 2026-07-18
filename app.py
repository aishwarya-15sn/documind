# import packages:
import streamlit as st
from PyPDF2 import PdfReader
import pandas as pd

# imports for langchain
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.chains.question_answering import load_qa_chain
from langchain.prompts import PromptTemplate

from datetime import datetime
import time

# to get text from pdf
def get_pdf_text(pdf_docs):
    text=""
    for pdf in pdf_docs:
        pdf_reader=PdfReader(pdf)
        for page in pdf_reader.pages:
            extracted=page.extract_text()
            if extracted:  
                text += extracted
    return text

# to get chunks from text
def get_text_chunks(text,model_name):
    if model_name=="Google AI":
        text_splitter=RecursiveCharacterTextSplitter(chunk_size=1500,chunk_overlap=150)
        return text_splitter.split_text(text)
    return []

@st.cache_resource
def load_embeddings():
    return HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )

# embedding the chunks and storing them in a vector store
def get_vector_store(text_chunks, model_name, api_key=None):
    if model_name == "Google AI":
        embeddings=load_embeddings()
        try:
            vector_store=FAISS.from_texts(text_chunks, embedding=embeddings)
            vector_store.save_local("./faiss_index")
            return vector_store
        except Exception as e:
            st.write(e)
            raise

def generate_summary(pdf_docs, api_key):
    if not pdf_docs:
        st.warning("Please upload PDF documents first.")
        return

    text=get_pdf_text(pdf_docs)

    # Reduce input size to avoid quota exhaustion
    MAX_CHARS=6000
    text=text[:MAX_CHARS]

    prompt=f"""
You are an intelligent document analyst.

Generate a concise but informative summary.

Include:
• Main Topics
• Key Findings
• Important People / Organizations
• Final Conclusion

Document:
{text}
"""

    try:
        model=ChatGoogleGenerativeAI(model="gemini-flash-latest", google_api_key=api_key, temperature=0.3)
        try:
            response=model.invoke(prompt)
        except Exception as e:
            if "prepayment credits are depleted" in str(e):
                st.error("🚫 Your Gemini API project has no remaining credits. Please recharge your AI Studio project or use another API key.")
            elif "429" in str(e):
                st.exception(e)
            else:
                st.error(f"Error: {e}")
            return
        
        st.subheader("📄 Document Summary")
        st.markdown(response.content)

    except Exception as e:
        if "429" in str(e) or "ResourceExhausted" in str(e):
            st.error("🚫 Gemini API quota exceeded. Please wait about a minute and try again, or use another API key.")
        else:
            if "prepayment credits are depleted" in str(e):
                st.error("🚫 Your Gemini API project has no remaining credits. Please recharge your AI Studio project or use another API key.")
            elif "429" in str(e):
                st.exception(e)
            else:
                st.error(f"Error: {e}")

# to take the user input
def user_input(user_question,model_name,api_key,pdf_docs,conversation_history):
    if api_key is None or pdf_docs is None:
        st.warning("Please upload any PDF and provide an API key.")
        return
    user_question_output=""
    response_output=""

    if model_name=="Google AI":
        embeddings=load_embeddings()
        import os
        if not os.path.exists("./faiss_index"):
            st.warning("Please click 'Submit & Process' before asking questions.")
            return
        faiss_db=FAISS.load_local("./faiss_index", embeddings, allow_dangerous_deserialization=True)
        
        # search for similar chunks
        docs=faiss_db.similarity_search(user_question)

        context="\n\n".join([doc.page_content for doc in docs])

        prompt=f"""
        Answer the question using only the provided context.

        Context:
        {context}

        Question:
        {user_question}

        Answer:
        """
        model=ChatGoogleGenerativeAI(
            model="gemini-flash-latest",
            google_api_key=api_key,
            temperature=0.3
        )

        try:
            response=model.invoke(prompt)
        except Exception as e:
            if "prepayment credits are depleted" in str(e):
                st.error("🚫 Your Gemini API project has no remaining credits. Please recharge your AI Studio project or use another API key.")
            elif "429" in str(e):
                st.exception(e)
            elif "ResourceExhausted" in str(e):
                st.exception(e)
            else:
                st.error(f"Error: {e}")
            return


        user_question_output=user_question
        response_output=response.content
        pdf_names=[pdf.name for pdf in pdf_docs] if pdf_docs else []
        conversation_history.append((user_question_output,response_output,model_name,datetime.now().strftime("%Y-%m-%d %H:%M:%S"),", ".join(pdf_names)))
        
        st.divider()
        st.subheader("Answer")

        if response_output.strip():
            st.markdown(response_output)
        else:
            st.write("Answer is not available in the context.")

    # creating csv file for chat history
    if len(st.session_state.conversation_history)>0:
        df=pd.DataFrame(st.session_state.conversation_history, columns=["Question","Answer","Model","Timestamp","PDF Name"])
        csv=df.to_csv(index=False)
        st.sidebar.download_button(label="📥 Download Chat History", data=csv, file_name="documind_chat_history.csv", mime="text/csv")      
        st.markdown("Click **Download Chat History** from the sidebar to save the conversation.")

def main():
    st.set_page_config(page_title="DocuMind",page_icon="📄")
    st.title("📄 DocuMind")
    st.caption("Enterprise AI Document Intelligence Platform powered by Retrieval-Augmented Generation (RAG).")    
    st.divider()
    if "conversation_history" not in st.session_state:
        st.session_state.conversation_history=[]
    model_name=st.sidebar.radio("Select the Model:", ["Google AI"])

    if model_name == "Google AI":
        api_key=st.secrets["GOOGLE_API_KEY"]

    with st.sidebar:
        st.title("Menu:")
        col1,col2=st.columns(2)
        reset_button=col2.button("Reset")
        clear_button=col1.button("Clear Chat")
        if reset_button:
            import os
            import shutil
            
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            
            if os.path.exists("faiss_index"):
                shutil.rmtree("faiss_index")
                
            st.cache_data.clear()
            st.cache_resource.clear()
            st.rerun()

        else:
            if clear_button:
                st.session_state.conversation_history=[]
                if "user_question" in st.session_state:
                    del st.session_state["user_question"]
                st.rerun()

        pdf_docs=st.file_uploader("Upload one or more PDF documents", accept_multiple_files=True, key="pdf_uploader")
        if pdf_docs:
            if st.button("📄 Generate Summary"):
                with st.spinner("Generating Summary..."):
                    generate_summary(pdf_docs, api_key)
                    
            st.sidebar.success(f"{len(pdf_docs)} document(s) uploaded")
            for pdf in pdf_docs:
                st.sidebar.write(f"📄 {pdf.name}")
        st.divider()
        st.subheader("About")
        st.info("""
                📄 Upload one or more PDF documents
                🔍 Ask questions in natural language
                🧠 Semantic search using FAISS
                🤖 AI-generated answers using Gemini""")
        if st.button("Submit & Process"):
            if pdf_docs:
                total_pages=0
                for pdf in pdf_docs:
                    reader=PdfReader(pdf)
                    total_pages += len(reader.pages)

                with st.spinner("Reading PDFs • Creating Embeddings • Building Knowledge Base..."):
                    text=get_pdf_text(pdf_docs)
                    chunks=get_text_chunks(text, model_name)
                    get_vector_store(chunks, model_name, api_key)

                st.sidebar.subheader("📊 Document Analytics")
                st.sidebar.metric("Documents", len(pdf_docs))
                st.sidebar.metric("Pages", total_pages)
                st.sidebar.metric("Chunks", len(chunks))
                st.sidebar.write("Embedding: all-MiniLM-L6-v2")
                st.sidebar.write("LLM: Gemini Flash Latest")
                st.success("Knowledge Base Ready. You can now ask questions.")

            else:
                st.warning("Please upload PDF files before processing.")
    
    user_question=st.text_input("Ask a question", placeholder="Example: Summarize the uploaded documents", key="user_question")
    if user_question:
        user_input(user_question,model_name,api_key,pdf_docs,st.session_state.conversation_history)
        
        st.divider()
        st.caption("Built by Aishwarya S N | Python • Streamlit • LangChain • FAISS • Google Gemini Flash")

if __name__=="__main__":
    main()
