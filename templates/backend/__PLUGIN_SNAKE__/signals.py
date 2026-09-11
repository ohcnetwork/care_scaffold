"""Signal receivers.

This is how a plugin reacts to core events without core knowing it exists.
Registered from AppConfig.ready() — never import this module anywhere else.

Example:

    from django.db.models.signals import post_save
    from django.dispatch import receiver
    from care.emr.models import TokenBooking

    @receiver(post_save, sender=TokenBooking)
    def on_booking_created(sender, instance, created, **kwargs):
        if not created:
            return
        ...
"""
