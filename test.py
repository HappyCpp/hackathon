from openai import OpenAI

client = OpenAI(
    api_key="sk-7a81f3d7726c4b5da64a172be92d8d52",
    base_url="https://api.deepseek.com/v1",  # 注意这里要加 /v1
)

response = client.chat.completions.create(
    model="deepseek-chat",
    messages=[{"role": "user", "content": "Hello"}],
    extra_headers={
        "Cookie": "HWWAFSESID=97cfe82f6d0dd04a64; HWWAFSESTIME=1755355732705"
    }
)

print(response.choices[0].message.content)  # 输出回复内容