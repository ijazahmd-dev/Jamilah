from cloudinary_storage.storage import StaticCloudinaryStorage

class AlwaysCloudinaryStaticStorage(StaticCloudinaryStorage):
    """
    Custom static storage that always returns the full HTTPS Cloudinary URL
    for static assets in production, regardless of DEBUG setting.
    """
    def url(self, name):
        return self._get_url(name)
