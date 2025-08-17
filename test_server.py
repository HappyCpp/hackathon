import requests


def test_sse():
    url = "http://localhost:5001/chat-stream"
    session_id = "test123"  # 可自定义或留空

    # 发起SSE请求
    with requests.get(f"{url}?session_id={session_id}", stream=True) as r:
        for line in r.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')
                if decoded_line.startswith('data:'):
                    print("Received:", decoded_line[5:].strip())


if __name__ == '__main__':
    test_sse()