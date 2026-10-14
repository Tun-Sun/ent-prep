from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (SubjectViewSet, TopicViewSet, QuestionViewSet, AssignmentViewSet,
                    AssignmentBlockViewSet, AssignmentAnswerViewSet, MyAssignmentViewSet)
from .import_views import (
    ExcelTemplateView,
    ExcelImportView,
    GoogleFormsImportView,
    GoogleFormsUrlImportView,
)

router = DefaultRouter()
router.register(r'subjects', SubjectViewSet, basename='subject')
router.register(r'topics', TopicViewSet, basename='topic')
router.register(r'questions', QuestionViewSet, basename='question')
router.register(r'assignments', AssignmentViewSet, basename='assignment')
router.register(r'assignment-blocks', AssignmentBlockViewSet, basename='assignment-block')
router.register(r'assignment-answers', AssignmentAnswerViewSet, basename='assignment-answer')
# ученик: свои уроки. Свой префикс, а не /assignments/:id/, потому что права там
# teacher/admin, а состав queryset для ученика — другой (назначенное ему и активное)
router.register(r'my/assignments', MyAssignmentViewSet, basename='my-assignment')

urlpatterns = router.urls + [
    path('import/template/', ExcelTemplateView.as_view(), name='excel-template'),
    path('import/excel/', ExcelImportView.as_view(), name='excel-import'),
    path('import/google-forms/', GoogleFormsImportView.as_view(), name='google-forms-import'),
    path('import/google-forms-url/', GoogleFormsUrlImportView.as_view(), name='google-forms-url-import'),
]
