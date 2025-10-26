from httpx import Response


def assert_response_code(response: Response, expected_code: int) -> None:
    assert (
        response.status_code == expected_code
    ), f"Unexpected response code {response.status_code}: {response.json()}"
