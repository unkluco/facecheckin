"""
Face recognition engine wrapper.
Fully isolated: imports image_object.py from the same directory (final/backend/).
"""

import sys
import os
from pathlib import Path
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Ensure this file's directory is on the path so image_object.py can be found locally
_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

try:
    from image_object import ImageObject
except ImportError as e:
    logger.error(f"Failed to import ImageObject: {e}")
    raise


class FaceEngine:
    """
    Face detection and recognition engine.
    Wraps ImageObject for processing images.
    """

    def __init__(self, db_path: str, threshold: float = 0.4):
        """
        Initialize FaceEngine.

        Args:
            db_path: Path to face database directory (e.g., model/Data/)
            threshold: Recognition threshold (0-1). Default: 0.4
        """
        self.db_path = str(db_path)
        self.threshold = threshold

        if not Path(self.db_path).exists():
            logger.error(f"Database path not found: {self.db_path}")

        logger.info(f"FaceEngine initialized with db_path={self.db_path}, threshold={threshold}")

    def process_image(self, input_path: str, output_path: str) -> Dict:
        """
        Process image: detect faces, recognize them, draw results.

        Args:
            input_path: Path to input image
            output_path: Path to save annotated image

        Returns:
            Dictionary with recognition results:
            {
                'labels': list of face labels,
                'faces': list of face dicts with details,
                'count': total faces detected,
                'known': list of recognized names,
                'unknown': list of unknown indices,
                'success': bool,
                'error': error message if any
            }
        """
        try:
            # Validate input
            if not os.path.exists(input_path):
                return {
                    'labels': [],
                    'faces': [],
                    'count': 0,
                    'known': [],
                    'unknown': [],
                    'success': False,
                    'error': f'Input image not found: {input_path}'
                }

            logger.info(f"Processing image: {input_path}")

            # Process image through pipeline
            img_obj = (
                ImageObject(input_path)
                .detect(expand_percentage=15, min_confidence=0.85)
                .recognize(db_path=self.db_path, threshold=self.threshold)
                .draw(known_color=(0, 255, 0), unknown_color=(0, 255, 255))
                .save_drawn(output_path)
            )

            # Extract results
            labels = img_obj.get_labels()
            face_data = img_obj.get_face_data()
            known_faces = img_obj.get_known_faces()

            # Build output
            known_labels = [f.label for f in known_faces]
            unknown_labels = [
                (i, l) for i, l in enumerate(labels)
                if l and l.startswith('unknown$')
            ]

            result = {
                'labels': labels,
                'faces': [
                    {
                        'label': f['label'],
                        'confidence': float(f['confidence']),
                        'is_known': f['is_known'],
                        'box': f['box'],
                        'box_expanded': f['box_expanded'],
                    }
                    for f in face_data
                ],
                'count': len(labels),
                'known': known_labels,
                'unknown': [u[1] for u in unknown_labels],
                'success': True,
                'error': None
            }

            logger.info(
                f"Successfully processed image: "
                f"{result['count']} faces detected, "
                f"{len(result['known'])} recognized"
            )

            return result

        except Exception as e:
            logger.error(f"Error processing image: {e}", exc_info=True)
            return {
                'labels': [],
                'faces': [],
                'count': 0,
                'known': [],
                'unknown': [],
                'success': False,
                'error': str(e)
            }

    def process_image_file(
        self,
        input_path: str,
        output_dir: str = None
    ) -> Dict:
        """
        Process image file and save results.

        Args:
            input_path: Path to input image
            output_dir: Directory to save output (optional)

        Returns:
            Processing results
        """
        # Generate output path
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            filename = Path(input_path).name
            output_path = os.path.join(output_dir, filename)
        else:
            output_path = input_path.replace('.jpg', '_result.jpg').replace('.png', '_result.png')

        return self.process_image(input_path, output_path)

    def extract_faces(self, input_path: str) -> List[Dict]:
        """
        Extract individual face crops from image.

        Args:
            input_path: Path to input image

        Returns:
            List of face data dictionaries
        """
        try:
            if not os.path.exists(input_path):
                return []

            img_obj = ImageObject(input_path).detect()
            return img_obj.get_face_data()

        except Exception as e:
            logger.error(f"Error extracting faces: {e}")
            return []

    def get_db_info(self) -> Dict:
        """
        Get information about the face database.

        Returns:
            Dictionary with database stats
        """
        try:
            db_path = Path(self.db_path)
            if not db_path.exists():
                return {'error': 'Database path not found'}

            people = [d for d in db_path.iterdir() if d.is_dir()]

            return {
                'db_path': self.db_path,
                'num_people': len(people),
                'people': [
                    {
                        'name': p.name,
                        'num_images': len(list(p.glob('*.jpg')))
                    }
                    for p in sorted(people)
                ]
            }

        except Exception as e:
            logger.error(f"Error getting database info: {e}")
            return {'error': str(e)}
