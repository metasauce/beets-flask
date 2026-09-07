class TestErrorHandling:
    """Tests our exception handling capabilities."""

    async def test_api_error(self, client):
        response = await client.get("/api_v1/error/api")
        data = await response.get_json()
        assert response.status_code == 500

        # Returned data is a SerializedException
        assert data["type"] == "ApiError"
        assert data["message"] == "This is a bad request"
        assert data["description"] is not None

    async def test_invalid_usage(self, client):
        response = await client.get("/api_v1/error/invalidUsage")
        data = await response.get_json()
        assert response.status_code == 400

        # Returned data is a SerializedException
        assert data["type"] == "InvalidUsageError"
        assert data["message"] == "This is a bad request"
        assert data["description"] is not None

    async def test_not_implemented(self, client):
        response = await client.get("/api_v1/error/notImplemented")
        data = await response.get_json()
        assert response.status_code == 501

        # Returned data is a SerializedException
        assert data["type"] == "NotImplementedError"
        assert data["message"] == "This is not implemented"
        assert data["description"] is not None

    async def test_integrity_error(self, client):
        response = await client.get("/api_v1/error/integrity")
        data = await response.get_json()
        assert response.status_code == 409

        # Returned data is a SerializedException
        assert data["type"] == "IntegrityError"
        assert data["message"] == "This is an integrity error"
        assert data["description"] is not None

    async def test_config_error(self, client):
        response = await client.get("/api_v1/error/configError")
        data = await response.get_json()
        assert response.status_code == 400

        # Returned data is a SerializedException
        assert data["type"] == "ConfigError"
        assert data["message"] == "This is a config error"
        assert data["description"] is not None

    async def test_file_not_found(self, client):
        response = await client.get("/api_v1/error/fileNotFound")
        data = await response.get_json()
        assert response.status_code == 404

        # Returned data is a SerializedException
        assert data["type"] == "FileNotFoundError"
        assert data["message"] == "This is a file not found error"
        assert data["description"] is not None

    async def test_generic_error(self, client):
        response = await client.get("/api_v1/error/genericError")
        data = await response.get_json()
        assert response.status_code == 500

        # Returned data is a SerializedException
        assert data["type"] == "Exception"
        assert data["message"] == "An unhandled exception occurred"
        assert data["description"] is not None
        assert data["trace"] is not None

    async def test_not_found(self, client):
        response = await client.get("/api_v1/error/notFound")
        data = await response.get_json()
        assert response.status_code == 404

        # Returned data is a SerializedException
        assert data["type"] == "NotFoundError"
        assert data["message"] == "This is a not found error"
        assert data["description"] is not None
