"""
Google Forms importer for ENT Prep.

Handles:
- Parsing Google Form responses/structure
- Downloading images from Drive
- Creating Question + Answer records
- Deduplication by external_id
"""

import os
import re
import json
import logging
from io import BytesIO
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from urllib.parse import urlparse, parse_qs

import requests
from django.core.files.base import ContentFile
from django.core.files.images import ImageFile
from django.db import transaction

from subjects.models import Subject, Topic, Question, Answer

logger = logging.getLogger(__name__)


class GoogleFormsImporter:
    """Imports questions from Google Forms or JSON export."""

    def __init__(self, subject: Subject, verify_on_import: bool = True):
        """
        Args:
            subject: Subject to import questions into
            verify_on_import: If True, mark imported questions as 'verified',
                            else 'draft' (for manual review by teacher)
        """
        self.subject = subject
        self.verify_on_import = verify_on_import
        self.imported_count = 0
        self.skipped_count = 0
        self.errors = []

    def import_from_json(self, json_data: Dict) -> Tuple[int, int, List[str]]:
        """
        Import questions from JSON structure.

        JSON format:
        {
            "form_id": "1....",
            "form_title": "Quiz: Physics Chapter 3",
            "questions": [
                {
                    "item_id": "123",
                    "question_text": "What is...",
                    "image_url": "https://drive.google.com/uc?id=...",
                    "answers": [
                        {"text": "A) ...", "is_correct": true},
                        ...
                    ],
                    "topic_name": "Mechanics",
                    "explanation": "Because..."
                }
            ]
        }

        Returns:
            (imported_count, skipped_count, error_list)
        """
        self.imported_count = 0
        self.skipped_count = 0
        self.errors = []

        form_id = json_data.get('form_id', '')
        questions = json_data.get('questions', [])

        logger.info(f"Starting import from form {form_id}: {len(questions)} questions")

        for item in questions:
            try:
                self._import_single_question(form_id, item)
            except Exception as e:
                self.skipped_count += 1
                error_msg = f"Question {item.get('item_id', '?')}: {str(e)}"
                self.errors.append(error_msg)
                logger.error(error_msg)

        logger.info(
            f"Import complete: {self.imported_count} imported, "
            f"{self.skipped_count} skipped"
        )
        return self.imported_count, self.skipped_count, self.errors

    @transaction.atomic
    def _import_single_question(self, form_id: str, item: Dict):
        """Import a single question with answers."""
        # Extract data
        item_id = item.get('item_id')
        question_text = item.get('question_text', '').strip()
        image_url = item.get('image_url', '').strip()
        answers_data = item.get('answers', [])
        topic_name = item.get('topic_name', 'General').strip()
        explanation = item.get('explanation', '').strip()

        if not question_text or not answers_data:
            raise ValueError("Missing question_text or answers")

        if not item_id:
            raise ValueError("Missing item_id")

        # Create external_id for deduplication
        external_id = f"{form_id}/{item_id}"

        # Check if already imported
        existing = Question.objects.filter(
            source_type='authorial',
            external_id=external_id,
        ).first()

        if existing:
            logger.debug(f"Question {external_id} already imported, skipping")
            self.skipped_count += 1
            return

        # Get or create topic
        topic, _ = Topic.objects.get_or_create(
            subject=self.subject,
            name=topic_name,
        )

        # Create question
        status = 'verified' if self.verify_on_import else 'draft'
        question = Question.objects.create(
            text=question_text,
            topic=topic,
            explanation=explanation,
            source_type='authorial',
            verification_status=status,
            external_id=external_id,
            language='ru',  # Default; could be expanded
            difficulty='medium',  # Default; could be extracted
        )

        # Download and attach image if present
        if image_url:
            try:
                self._attach_image_to_question(question, image_url)
            except Exception as e:
                logger.warning(f"Failed to download image for {external_id}: {e}")

        # Create answers
        for idx, ans_data in enumerate(answers_data):
            Answer.objects.create(
                question=question,
                text=ans_data.get('text', '').strip(),
                is_correct=ans_data.get('is_correct', False),
            )

        self.imported_count += 1
        logger.info(f"Imported question {external_id}")

    def _attach_image_to_question(self, question: Question, image_url: str):
        """Download image from URL and attach to question."""
        # Parse Google Drive share link or direct URL
        image_data = self._download_image(image_url)
        if not image_data:
            return

        # Save to question.image
        filename = f"q_{question.id}.jpg"
        question.image.save(filename, ImageFile(image_data), save=True)

    @staticmethod
    def _download_image(url: str) -> Optional[BytesIO]:
        """Download image from URL (Google Drive or direct)."""
        if not url:
            return None

        try:
            # Convert Google Drive share URL to direct download if needed
            url = GoogleFormsImporter._convert_drive_url(url)

            response = requests.get(url, timeout=10)
            response.raise_for_status()

            # Validate it's an image
            content_type = response.headers.get('Content-Type', '')
            if 'image' not in content_type:
                logger.warning(f"URL did not return image: {content_type}")
                return None

            return BytesIO(response.content)
        except Exception as e:
            logger.error(f"Failed to download image from {url}: {e}")
            return None

    @staticmethod
    def _convert_drive_url(url: str) -> str:
        """
        Convert Google Drive share URLs to direct download.

        Examples:
            https://drive.google.com/file/d/{ID}/view?usp=...
            -> https://drive.google.com/uc?id={ID}&export=download

            https://drive.google.com/open?id={ID}
            -> https://drive.google.com/uc?id={ID}&export=download
        """
        # Extract ID from /file/d/{ID}/view
        match = re.search(r'/file/d/([a-zA-Z0-9-_]+)', url)
        if match:
            file_id = match.group(1)
            return f"https://drive.google.com/uc?id={file_id}&export=download"

        # Extract ID from ?id=...
        match = re.search(r'[?&]id=([a-zA-Z0-9-_]+)', url)
        if match:
            file_id = match.group(1)
            return f"https://drive.google.com/uc?id={file_id}&export=download"

        # Return as-is if already a direct URL
        return url


def parse_google_form_export(html_content: str) -> Dict:
    """
    Parse exported Google Form HTML.

    This is a simplified parser. For production, consider using
    google-forms-to-quiz or similar library.

    Returns dict matching import_from_json format.
    """
    # Placeholder: actual implementation depends on Form export format.
    # Could extract JSON from embedded script tags, parse HTML structure, etc.
    raise NotImplementedError(
        "HTML parsing not yet implemented. Use JSON export with Google Forms API instead."
    )
