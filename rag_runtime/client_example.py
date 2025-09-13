import json, requests, sys

URL = "http://localhost:8000/multimodal_infer"
IMG = sys.argv[1] if len(sys.argv) > 1 else "chexpert/train/patient00108/study1/view2_lateral.jpg"

payload = {
  "utterances": [
    "patient: I’ve had fever and productive cough for 2 days.",
    "doctor: any chest pain or shortness of breath?",
    "patient: mild shortness of breath on exertion."
  ]
}

files = {
  "payload": (None, json.dumps(payload), "application/json"),
  "file": ("xray.jpg", open(IMG, "rb"), "application/octet-stream"),
}

r = requests.post(URL, files=files, timeout=120)
print(json.dumps(r.json(), indent=2))
