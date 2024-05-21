import pandas as pd
from datetime import datetime
import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv

load_dotenv()

CLASSIFICATION_ENDPOINT = os.getenv('CLASSIFICATION_ENDPOINT')
API_KEY = os.getenv('API_KEY')


def post_with_retry(endpoint, payload, files):
    session = requests.Session()
    adapter = HTTPAdapter(
        max_retries=Retry(
            total=5,
            backoff_factor=0.1,  # retry after: {backoff factor} * (2 ** ({retry number} - 1)) seconds
            status_forcelist=[
                429,
                500,
                502,
                503,
                504,
            ],  # retry after: 429: Too Many Requests, 500: Internal Server Error, 502: Bad Gateway, 503: Service Unavailable, 504: Gateway Timeout
        )
    )
    session.mount("https://", adapter)
    return session.post(
        endpoint, data=payload, files=files, headers={"access_token": API_KEY}
    )


def send_track_data(track_id, save_path, rec_start_format):

    if not os.path.exists(os.path.join(save_path, f"{rec_start_format}_metadata.csv")):
        return

    metadata = pd.read_csv(os.path.join(save_path, f"{rec_start_format}_metadata.csv"))

    track_data = metadata[metadata['track_ID'] == track_id]

    if track_data.empty:
        return

    start_date = datetime.strptime(track_data['timestamp'].min(), '%Y-%m-%dT%H:%M:%S.%f')
    end_date = datetime.strptime(track_data['timestamp'].max(), '%Y-%m-%dT%H:%M:%S.%f')
    duration = int((end_date - start_date).total_seconds())

    track_files = [f for f in os.listdir(os.path.join(save_path, 'crop', 'insect')) if f'ID{track_id}' in f.split('_')]
    file_paths = [os.path.join(save_path, 'crop', 'insect', f) for f in track_files]

    endpoint = f'{CLASSIFICATION_ENDPOINT}/{track_id}'

    payload = {'start_date': start_date, 'end_date': end_date, 'duration_s': duration}
    files = [('files', open(fp, 'rb')) for fp in file_paths]

    response = post_with_retry(endpoint, payload, files)
    print(response)
