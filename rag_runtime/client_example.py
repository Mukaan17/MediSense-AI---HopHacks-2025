import requests, json

URL = "http://localhost:8000/infer"

sample = {
  "utterances": [
    "patient: hi doctor, I drank too much caffine.",
    "doctor: any chest pain or neuro symptoms like weakness or slurred speech?",
    "patient: no chest pain, I took 600mg caffine",
    "doctor: that's too much",
    "patient: I have nothing, I ate only 600 calories but burned 1200 calories by working out."
  ]
}

def main():
    r = requests.post(URL, json=sample, timeout=60)
    print(json.dumps(r.json(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()


