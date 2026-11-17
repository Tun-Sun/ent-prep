from django.db import models


class TrackChoices(models.TextChoices):
    """Учебный трек: школьная программа, ЕНТ или NUET.

    Один список на всю платформу. `Subject.track` пустой означает «общий
    предмет» — он виден всем трекам, поэтому новые предметы без явного выбора
    не исчезают у половины учеников.
    """
    SCHOOL = 'school', 'Школа'
    ENT = 'ent', 'ЕНТ'
    NUET = 'nuet', 'NUET'
