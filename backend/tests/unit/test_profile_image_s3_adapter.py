from backend.app.integrations.s3.profile_image import S3ProfileImageAdapter


class FakeS3Client:
    def __init__(self) -> None:
        self.put_calls: list[dict[str, object]] = []
        self.deleted: list[dict[str, object]] = []

    def put_object(self, **kwargs: object) -> dict[str, object]:
        self.put_calls.append(kwargs)
        return {}

    def delete_object(self, **kwargs: object) -> dict[str, object]:
        self.deleted.append(kwargs)
        return {}

    def generate_presigned_url(
        self, ClientMethod: str, Params: dict[str, str], ExpiresIn: int
    ) -> str:
        assert ClientMethod == "get_object"
        assert Params["Key"].startswith("profile-images/")
        assert ExpiresIn == 300
        return "https://s3.example.test/private"


def test_profile_image_adapter_is_scoped_to_its_private_prefix() -> None:
    client = FakeS3Client()
    adapter = S3ProfileImageAdapter(
        client, bucket="exercise-media", prefix="profile-images/", expiry_seconds=300
    )

    assert adapter.put("profile-images/user/image.png", b"image", "image/png") is True
    assert adapter.create_url("profile-images/user/image.png") == "https://s3.example.test/private"
    assert adapter.delete("profile-images/user/image.png") is True
    assert adapter.put("videos/0001-source.gif", b"image", "image/gif") is False
    assert adapter.create_url("videos/0001-source.gif") is None
    assert client.put_calls[0]["Key"] == "profile-images/user/image.png"
    assert client.deleted[0]["Key"] == "profile-images/user/image.png"
