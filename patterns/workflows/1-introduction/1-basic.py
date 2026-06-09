import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
api_key=os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

question = input("Ask a question: ")

completion = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "You're a helpful assistant."},
        {
            "role": "user",
            "content": question,
        },
    ],
)
completion.model_dump()
response = completion.choices[0].message.content
print(response)
