from whitenoise.storage import CompressedManifestStaticFilesStorage


class StaticFilesStorage(CompressedManifestStaticFilesStorage):
    """Content-hashed, compressed static files that tolerate broken references.

    Hashed names (style.4f1c2a9e.css) let WhiteNoise serve files with a
    one-year "immutable" cache. While hashing, Django also rewrites every file
    a CSS/JS file points to; some third-party files (Jazzmin's Bootstrap
    bundle) point to source maps they don't ship, which would fail
    collectstatic and with it the deploy. Such references are left as they are.
    """

    manifest_strict = False

    def hashed_name(self, name, content=None, filename=None):
        try:
            return super().hashed_name(name, content, filename)
        except ValueError:
            return name
