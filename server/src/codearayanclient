import requests

SERVER_URL = "http://localhost:8000"
history = []

print("Chat démarré (Ctrl+C pour quitter)\n")

while True:
    user_input = input("Toi: ").strip()
    if not user_input:
        continue

    payload = {
        "message": user_input,
        "history": history
    }

    response = requests.post(f"{SERVER_URL}/chat", json=payload)

    if response.status_code == 200:
        reply = response.json()["reply"]
        print(f"IA: {reply}\n")

        # Maintenir l'historique côté client
        # Attention : Gemini utilise "model" et non "assistant"
        history.append({"role": "user", "content": user_input})
        history.append({"role": "model", "content": reply})
    else:
        print(f"Erreur {response.status_code}: {response.json()}")