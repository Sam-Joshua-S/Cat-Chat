import streamlit as st
from langchain.llms import LlamaCpp
from langchain.prompts import PromptTemplate
# from langchain.callbacks.manager import CallbackManager
from langchain.callbacks.base import BaseCallbackHandler
from huggingface_hub import hf_hub_download
import redis
import re
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Access the variables in your code

redis_host = st.secrets["REDIS_HOST"]
redis_port = st.secrets["REDIS_PORT"]
redis_password = st.secrets["REDIS_PASSWORD"]




redis_client = redis.StrictRedis(
    host=redis_host,
    port=redis_port,
    password=redis_password,
    decode_responses=True,  # Decode responses to strings
)

class StreamHandler(BaseCallbackHandler):
    def __init__(self, container, initial_text=""):
        self.container = container
        self.text = initial_text

    def on_llm_new_token(self, token: str, **kwargs) -> None:
        self.text += token
        self.container.markdown(self.text)


@st.cache_resource
def create_chain(system_prompt):
    (repo_id, model_file_name) = ("TheBloke/Mistral-7B-Instruct-v0.1-GGUF",
                                  "mistral-7b-instruct-v0.1.Q4_0.gguf")

    model_path = hf_hub_download(repo_id=repo_id,
                                 filename=model_file_name,
                                 repo_type="model")

    llm = LlamaCpp(
            model_path=model_path,
            temperature=0,
            max_tokens=512,
            top_p=1,
            stop=["[INST]"],
            verbose=False,
            streaming=True,
            )

    template = """
    <s>[INST]{}[/INST]</s>

    [INST]{}[/INST]
    """.format(system_prompt, "{question}")

    prompt = PromptTemplate(template=template, input_variables=["question"])

    llm_chain = prompt | llm  

    return llm_chain

st.set_page_config(
    page_title="Your Assistant Cat!"
)

st.header("Your Assistant Cat!")

system_prompt = st.text_area(
    label="System Prompt",
    value="You are a helpful AI assistant who answers questions in short sentences.Your are an cat so say meow at end of sentence.",
    key="system_prompt")

llm_chain = create_chain(system_prompt)

if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "How may I help you today?"}
    ]

if "current_response" not in st.session_state:
    st.session_state.current_response = ""

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if user_prompt := st.chat_input("Your message here", key="user_input"):
    
    processed_user_prompt = re.sub('\s+', ' ', user_prompt).strip().lower()

    cached_answer = redis_client.get(processed_user_prompt)

    if cached_answer:
        response = cached_answer
    else:
        response = llm_chain.invoke({"question": user_prompt})

        redis_client.setex(name=processed_user_prompt, time=3600, value=response)


    st.session_state.messages.append(
        {"role": "user", "content": user_prompt}
    )

    # Add our input to the chat window
    with st.chat_message("user"):
        st.markdown(user_prompt)


    # Add the response to the session state
    st.session_state.messages.append(
        {"role": "assistant", "content": response}
    )

    # Add the response to the chat window
    with st.chat_message("assistant"):
        st.markdown(response)


st.sidebar.title("Chat Options")
if st.sidebar.button("New Chat"):
    st.cache_data.clear()

    # Clear previous messages and reset the chat
    st.empty()
    st.session_state.messages = [
        {"role": "assistant", "content": "How may I help you today?"}
    ]
    

# Display previous conversations in the sidebar
st.sidebar.subheader("Previous Questions")
question_indices = []
for idx, message in enumerate(st.session_state.messages[-20:]):  # Display the last 5 messages
    if message['role'] == 'user':
        if st.sidebar.button(f"Question {int((idx + 1) / 2)}: {message['content']}", key=f"button_{idx}"):
            # Store the corresponding index of the answer in the main chat
            question_indices.append(idx + 1)

if st.session_state.messages[-1]['role'] == 'assistant':
    response_index = len(st.session_state.messages) - 1  
    if response_index in question_indices:
        st.write(f"<script>window.scrollTo(0, document.body.scrollHeight);</script>", unsafe_allow_html=True)
