from django.apps import AppConfig


class WebsiteConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'website'

    def ready(self):
        # Import signals safely
        try:
            import website.signals  # noqa: F401
        except Exception:
            pass

        # Register coordinate auto-assignment signal
        try:
            from django.db.models.signals import pre_save
            from website.coordinate_signals import auto_assign_coordinates
            from website.models import RentalPost
            pre_save.connect(auto_assign_coordinates, sender=RentalPost)
        except Exception as e:
            print(f"Warning: Could not register coordinate signal: {e}")

        # --- Fix triệt để lỗi __proxy__ trong các model __str__ ---
        try:
            from allauth.socialaccount import models as social_models

            def _wrap_str(orig):
                def _s(self):
                    try:
                        val = orig(self)
                        # Ép sang chuỗi thật nếu không phải str
                        if not isinstance(val, str):
                            val = str(val)
                        return val
                    except Exception:
                        # Fallback: hiển thị PK để không lỗi
                        pk = getattr(self, 'pk', None)
                        return str(pk) if pk is not None else ''
                return _s

            # Áp dụng cho các model dễ bị lỗi của allauth
            for name in ('SocialAccount', 'SocialApp', 'SocialToken'):
                cls = getattr(social_models, name, None)
                if cls and hasattr(cls, '__str__'):
                    try:
                        cls.__str__ = _wrap_str(cls.__str__)
                    except Exception:
                        pass
        except Exception:
            # allauth có thể chưa cài, bỏ qua
            pass
