import streamlit as st
import json
import requests


def stream_chat_response(
    query: str,
    api_url: str = (
        f"https://{st.secrets["RUNPOD_ID"]}"
        ".api.runpod.ai/api/v1/ask"
    )
):
    query = query.strip()
    try:
        response = requests.post(
            url=api_url,
            json={
                "question": f"""\
<|im_start|>system
Bạn là một trợ lí Tiếng Việt nhiệt tình và trung thực. \
Hãy luôn trả lời một cách hữu ích nhất có thể.<|im_end|>
<|im_start|>user
Chú ý các yêu cầu sau:
- Nếu câu hỏi là một lời chào hay tạm biệt, hãy đáp lại lời \
chào hỏi một cách phù hợp.
- Hãy trả lời câu hỏi một cách ngắn gọn súc tích.

### Câu hỏi :
{query}

### Trả lời :<|im_end|>
<|im_start|>assistant
"""
            },
            headers={
            "Accept": "text/event-stream",
            "Authorization": (
                    f"Bearer {st.secrets["RUNPOD_API_KEY"]}"
                )
            },
            stream=True
        )
        response.raise_for_status()
        # source = []
        for line in response.iter_lines(decode_unicode=True):
            if line.startswith("data: "):
                try:
                    data: dict = json.loads(line[6:])  # Remove "data: " prefix
                    if (
                        data["type"] == "done"
                        or data["type"] == "retrieval_error"
                        or data["type"] == "generation_error"
                    ):
                        yield data
                        break
                    else:
                        yield data
                except json.JSONDecodeError:
                    continue  # Skip malformed JSON
    except requests.exceptions.RequestException as e:
        st.error(f"Error connecting to API: {e}")
        return


def stream_upload_response(
    files_data,
    api_url: str = "http://localhost:8000/api/v1/upload"
):
    try:
        response = requests.post(
            url=api_url,
            files=files_data,
            headers={"Accept": "text/event-stream"},
            stream=True
        )
        response.raise_for_status()
        for line in response.iter_lines(decode_unicode=True):
            if line.startswith("data: "):
                try:
                    data: dict = json.loads(line[6:])  # Remove "data: " prefix
                    if (
                        data["type"] == "upload_status"
                        or data["type"] == "upload_task"
                    ):
                        yield data
                    else:
                        yield data
                        break
                except json.JSONDecodeError:
                    continue  # Skip malformed JSON
    except requests.exceptions.RequestException as e:
        return {
            "generation_error" : f"Error connecting to API: {e}"
        }


# Initialize questions history
if "questions" not in st.session_state:
    st.session_state.questions = []
# Initialize replies history
if "replies" not in st.session_state:
    st.session_state.replies = []
# Initialize sources history
if "sources" not in st.session_state:
    st.session_state.sources = []
if "statuses" not in st.session_state:
    st.session_state.statuses = []

st.title("Runpod VLLM Chatbot Test")
tab1, tab2 = st.tabs(["Chat", "Upload"])

with tab1:
    chat_container = st.container(height=450, border=False)
    with chat_container:
        # Display chat messages from history on app rerun
        for i in range(len(st.session_state.questions)):
            question: dict = st.session_state.questions[i]
            reply: dict = st.session_state.replies[i]
            source: str = st.session_state.sources[i]
            status: str = st.session_state.statuses[i]
            with st.chat_message(question["role"]):
                st.markdown(question["content"])
            with st.chat_message(reply["role"]):
                st.markdown(status)
                st.markdown(reply["content"])
            if source != "none":
                with st.expander("Source"):
                    st.markdown(
                        f"From: [{source}]"
                        f"(http://127.0.0.1:8000/api/v1/docs/{source})"
                    )
    # React to user input
    if prompt := st.chat_input("Ask a question"):
        if prompt.strip():
            with chat_container:
                # Display user message in chat message container
                with st.chat_message("user"):
                    st.markdown(prompt)
                # Add user message to chat history
                st.session_state.questions.append(
                    {
                        "role": "user", "content": prompt
                    }
                )
                source: str = "none"
                with st.chat_message("assistant"):
                    status_placeholder = st.empty()
                    message_placeholder = st.empty()
                    full_response: str = ""
                    status: str = ""
                    # Stream the response
                    try:
                        for event in stream_chat_response(prompt):
                            if event["type"] == "source":
                                source = event["data"]
                            elif event["type"] == "status":
                                status = event["data"]
                                status_placeholder.markdown(event["data"])
                            elif event["type"] == "retrieval_error":
                                status = "An error occured"
                                status_placeholder.markdown(event["data"])
                                message_placeholder.markdown("Server Error")
                            elif event["type"] == "generation_error":
                                status = "An error occured"
                                status_placeholder.markdown(event["data"])
                                message_placeholder.markdown("Server Error")
                            elif event["type"] == "answer_part":
                                full_response += event["data"]
                                message_placeholder.markdown(full_response + "▌")
                            elif event["type"] == "done":
                                message_placeholder.markdown(full_response)
                                break
                    except Exception as e:
                        status = "An error occured"
                        status_placeholder.markdown("An error occured")
                        full_response = f"Error: {e}"
                        message_placeholder.markdown(full_response)
                # Add assistant response to chat history
                st.session_state.statuses.append(status)
                st.session_state.replies.append(
                    {
                        "role": "assistant",
                        "content": full_response
                    }
                )
                # Create collapsible area to display sources
                if source != "none":
                    with st.expander("Source"):
                        st.markdown(
                            f"From: [{source}]"
                            f"(http://127.0.0.1:8000/api/v1/docs/{source})"
                        )
                st.session_state.sources.append(source)

with tab2:
    files = st.file_uploader(
        label="Upload documents",
        accept_multiple_files=True,
        key="uploader"
    )
    if files and st.button("Upload files"):
        file_names = [file.name for file in files]
        files_data = [
            (
                "files", (file.name, file.getbuffer(), file.type)
            ) for file in files
        ]
        with st.status("Downloading data...", expanded=True) as status:
            for event in stream_upload_response(files_data=files_data):
                if event["type"] == "upload_done":
                    status.update(
                        label=event["data"],
                        state="complete",
                        expanded=False
                    )
                    break
                elif event["type"] == "upload_failed":
                    status.update(
                        label=event["data"],
                        state="error",
                        expanded=False
                    )
                    break
                elif event["type"] == "upload_task":
                    status.update(
                        label=event["data"],
                        state="running",
                        expanded=True
                    )
                    st.write(event["data"])
                else:
                    st.write(event["data"])
