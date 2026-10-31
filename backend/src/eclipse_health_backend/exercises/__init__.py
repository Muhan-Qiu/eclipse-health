"""运动记录：复用核心 ``records`` 表，记录类型 ``org.eclipsehealth.health.exercise``。"""

from .models import EXERCISE_RECORD_TYPE, Exercise, ExerciseCreate, ExercisePage, ExerciseUpdate

__all__ = [
    "EXERCISE_RECORD_TYPE",
    "Exercise",
    "ExerciseCreate",
    "ExercisePage",
    "ExerciseUpdate",
]
