from time import sleep
from typing import Any, List, Optional, Tuple

import cv2
import numpy

from facefusion import process_manager, state_manager
from facefusion.common_helper import get_first
from facefusion.download import conditional_download
from facefusion.execution import create_inference_session
from facefusion.face_helper import apply_nms, convert_to_face_landmark_5, create_rotated_matrix_and_size, create_static_anchors, distance_to_bounding_box, distance_to_face_landmark_5, estimate_face_angle_from_face_landmark_68, estimate_matrix_by_face_landmark_5, get_nms_threshold, normalize_bounding_box, transform_bounding_box, transform_points, warp_face_by_face_landmark_5, warp_face_by_translation
from facefusion.face_store import get_static_faces, set_static_faces
from facefusion.filesystem import is_file, resolve_relative_path
from facefusion.thread_helper import conditional_thread_semaphore, thread_lock, thread_semaphore
from facefusion.typing import Angle, BoundingBox, Embedding, Face, FaceLandmark5, FaceLandmark68, FaceLandmarkSet, FaceScoreSet, ModelSet, Score, VisionFrame
from facefusion.vision import resize_frame_resolution, unpack_resolution

FACE_ANALYSER = None
MODELS : ModelSet =\
{
	'face_detector_retinaface':
	{
		'url': 'https://github.com/facefusion/facefusion-assets/releases/download/models/retinaface_10g.onnx',
		'path': resolve_relative_path('../.assets/models/retinaface_10g.onnx')
	},
	'face_detector_scrfd':
	{
		'url': 'https://github.com/facefusion/facefusion-assets/releases/download/models/scrfd_2.5g.onnx',
		'path': resolve_relative_path('../.assets/models/scrfd_2.5g.onnx')
	},
	'face_detector_yoloface':
	{
		'url': 'https://github.com/facefusion/facefusion-assets/releases/download/models/yoloface_8n.onnx',
		'path': resolve_relative_path('../.assets/models/yoloface_8n.onnx')
	},
	'face_recognizer_arcface_blendswap':
	{
		'url': 'https://github.com/facefusion/facefusion-assets/releases/download/models/arcface_w600k_r50.onnx',
		'path': resolve_relative_path('../.assets/models/arcface_w600k_r50.onnx')
	},
	'face_recognizer_arcface_ghost':
	{
		'url': 'https://github.com/facefusion/facefusion-assets/releases/download/models/arcface_ghost.onnx',
		'path': resolve_relative_path('../.assets/models/arcface_ghost.onnx')
	},
	'face_recognizer_arcface_inswapper':
	{
		'url': 'https://github.com/facefusion/facefusion-assets/releases/download/models/arcface_w600k_r50.onnx',
		'path': resolve_relative_path('../.assets/models/arcface_w600k_r50.onnx')
	},
	'face_recognizer_arcface_simswap':
	{
		'url': 'https://github.com/facefusion/facefusion-assets/releases/download/models/arcface_simswap.onnx',
		'path': resolve_relative_path('../.assets/models/arcface_simswap.onnx')
	},
	'face_recognizer_arcface_uniface':
	{
		'url': 'https://github.com/facefusion/facefusion-assets/releases/download/models/arcface_w600k_r50.onnx',
		'path': resolve_relative_path('../.assets/models/arcface_w600k_r50.onnx')
	},
	'face_landmarker_68':
	{
		'url': 'https://github.com/facefusion/facefusion-assets/releases/download/models/2dfan4.onnx',
		'path': resolve_relative_path('../.assets/models/2dfan4.onnx')
	},
	'face_landmarker_68_5':
	{
		'url': 'https://github.com/facefusion/facefusion-assets/releases/download/models/face_landmarker_68_5.onnx',
		'path': resolve_relative_path('../.assets/models/face_landmarker_68_5.onnx')
	},
	'gender_age':
	{
		'url': 'https://github.com/facefusion/facefusion-assets/releases/download/models/gender_age.onnx',
		'path': resolve_relative_path('../.assets/models/gender_age.onnx')
	}
}


def get_face_analyser() -> Any:
	global FACE_ANALYSER

	face_detectors = {}
	face_recognizer = None
	face_landmarkers = {}

	with thread_lock():
		while process_manager.is_checking():
			sleep(0.5)
		if FACE_ANALYSER is None:
			if state_manager.get_item('face_detector_model') in [ 'many', 'retinaface' ]:
				face_detectors['retinaface'] = create_inference_session(MODELS.get('face_detector_retinaface').get('path'), state_manager.get_item('execution_device_id'), state_manager.get_item('execution_providers'))
			if state_manager.get_item('face_detector_model') in [ 'many', 'scrfd' ]:
				face_detectors['scrfd'] = create_inference_session(MODELS.get('face_detector_scrfd').get('path'), state_manager.get_item('execution_device_id'), state_manager.get_item('execution_providers'))
			if state_manager.get_item('face_detector_model') in [ 'many', 'yoloface' ]:
				face_detectors['yoloface'] = create_inference_session(MODELS.get('face_detector_yoloface').get('path'), state_manager.get_item('execution_device_id'), state_manager.get_item('execution_providers'))
			if state_manager.get_item('face_recognizer_model') == 'arcface_blendswap':
				face_recognizer = create_inference_session(MODELS.get('face_recognizer_arcface_blendswap').get('path'), state_manager.get_item('execution_device_id'), state_manager.get_item('execution_providers'))
			if state_manager.get_item('face_recognizer_model') == 'arcface_ghost':
				face_recognizer = create_inference_session(MODELS.get('face_recognizer_arcface_ghost').get('path'), state_manager.get_item('execution_device_id'), state_manager.get_item('execution_providers'))
			if state_manager.get_item('face_recognizer_model') == 'arcface_inswapper':
				face_recognizer = create_inference_session(MODELS.get('face_recognizer_arcface_inswapper').get('path'), state_manager.get_item('execution_device_id'), state_manager.get_item('execution_providers'))
			if state_manager.get_item('face_recognizer_model') == 'arcface_simswap':
				face_recognizer = create_inference_session(MODELS.get('face_recognizer_arcface_simswap').get('path'), state_manager.get_item('execution_device_id'), state_manager.get_item('execution_providers'))
			if state_manager.get_item('face_recognizer_model') == 'arcface_uniface':
				face_recognizer = create_inference_session(MODELS.get('face_recognizer_arcface_uniface').get('path'), state_manager.get_item('execution_device_id'), state_manager.get_item('execution_providers'))
			face_landmarkers['68'] = create_inference_session(MODELS.get('face_landmarker_68').get('path'), state_manager.get_item('execution_device_id'), state_manager.get_item('execution_providers'))
			face_landmarkers['68_5'] = create_inference_session(MODELS.get('face_landmarker_68_5').get('path'), state_manager.get_item('execution_device_id'), state_manager.get_item('execution_providers'))
			gender_age = create_inference_session(MODELS.get('gender_age').get('path'), state_manager.get_item('execution_device_id'), state_manager.get_item('execution_providers'))
			FACE_ANALYSER =\
			{
				'face_detectors': face_detectors,
				'face_recognizer': face_recognizer,
				'face_landmarkers': face_landmarkers,
				'gender_age': gender_age
			}
	return FACE_ANALYSER


def clear_face_analyser() -> Any:
	global FACE_ANALYSER

	FACE_ANALYSER = None


def pre_check() -> bool:
	download_directory_path = resolve_relative_path('../.assets/models')
	model_urls =\
	[
		MODELS.get('face_landmarker_68').get('url'),
		MODELS.get('face_landmarker_68_5').get('url'),
		MODELS.get('gender_age').get('url')
	]
	model_paths =\
	[
		MODELS.get('face_landmarker_68').get('path'),
		MODELS.get('face_landmarker_68_5').get('path'),
		MODELS.get('gender_age').get('path')
	]

	if state_manager.get_item('face_detector_model') in [ 'many', 'retinaface' ]:
		model_urls.append(MODELS.get('face_detector_retinaface').get('url'))
		model_paths.append(MODELS.get('face_detector_retinaface').get('path'))
	if state_manager.get_item('face_detector_model') in [ 'many', 'scrfd' ]:
		model_urls.append(MODELS.get('face_detector_scrfd').get('url'))
		model_paths.append(MODELS.get('face_detector_scrfd').get('path'))
	if state_manager.get_item('face_detector_model') in [ 'many', 'yoloface' ]:
		model_urls.append(MODELS.get('face_detector_yoloface').get('url'))
		model_paths.append(MODELS.get('face_detector_yoloface').get('path'))
	if state_manager.get_item('face_detector_model') == 'arcface_blendswap':
		model_urls.append(MODELS.get('face_recognizer_arcface_blendswap').get('url'))
		model_paths.append(MODELS.get('face_recognizer_arcface_blendswap').get('path'))
	if state_manager.get_item('face_recognizer_model') == 'arcface_ghost':
		model_urls.append(MODELS.get('face_recognizer_arcface_ghost').get('url'))
		model_paths.append(MODELS.get('face_recognizer_arcface_ghost').get('path'))
	if state_manager.get_item('face_recognizer_model') == 'arcface_inswapper':
		model_urls.append(MODELS.get('face_recognizer_arcface_inswapper').get('url'))
		model_paths.append(MODELS.get('face_recognizer_arcface_inswapper').get('path'))
	if state_manager.get_item('face_recognizer_model') == 'arcface_simswap':
		model_urls.append(MODELS.get('face_recognizer_arcface_simswap').get('url'))
		model_paths.append(MODELS.get('face_recognizer_arcface_simswap').get('path'))
	if state_manager.get_item('face_recognizer_model') == 'arcface_uniface':
		model_urls.append(MODELS.get('face_recognizer_arcface_uniface').get('url'))
		model_paths.append(MODELS.get('face_recognizer_arcface_uniface').get('path'))

	if not state_manager.get_item('skip_download'):
		process_manager.check()
		conditional_download(download_directory_path, model_urls)
		process_manager.end()
	return all(is_file(model_path) for model_path in model_paths)


def detect_with_retinaface(vision_frame : VisionFrame, face_detector_size : str) -> Tuple[List[BoundingBox], List[FaceLandmark5], List[Score]]:
	face_detector = get_face_analyser().get('face_detectors').get('retinaface')
	face_detector_width, face_detector_height = unpack_resolution(face_detector_size)
	temp_vision_frame = resize_frame_resolution(vision_frame, (face_detector_width, face_detector_height))
	ratio_height = vision_frame.shape[0] / temp_vision_frame.shape[0]
	ratio_width = vision_frame.shape[1] / temp_vision_frame.shape[1]
	feature_strides = [ 8, 16, 32 ]
	feature_map_channel = 3
	anchor_total = 2
	bounding_boxes = []
	face_landmarks_5 = []
	face_scores = []

	detect_vision_frame = prepare_detect_frame(temp_vision_frame, face_detector_size)
	with thread_semaphore():
		detections = face_detector.run(None,
		{
			face_detector.get_inputs()[0].name: detect_vision_frame
		})

	for index, feature_stride in enumerate(feature_strides):
		keep_indices = numpy.where(detections[index] >= state_manager.get_item('face_detector_score'))[0]
		if numpy.any(keep_indices):
			stride_height = face_detector_height // feature_stride
			stride_width = face_detector_width // feature_stride
			anchors = create_static_anchors(feature_stride, anchor_total, stride_height, stride_width)
			bounding_box_raw = detections[index + feature_map_channel] * feature_stride
			face_landmark_5_raw = detections[index + feature_map_channel * 2] * feature_stride
			for bounding_box in distance_to_bounding_box(anchors, bounding_box_raw)[keep_indices]:
				bounding_boxes.append(numpy.array(
				[
					bounding_box[0] * ratio_width,
					bounding_box[1] * ratio_height,
					bounding_box[2] * ratio_width,
					bounding_box[3] * ratio_height,
				]))
			for face_landmark_5 in distance_to_face_landmark_5(anchors, face_landmark_5_raw)[keep_indices]:
				face_landmarks_5.append(face_landmark_5 * [ ratio_width, ratio_height ])
			for score in detections[index][keep_indices]:
				face_scores.append(score[0])
	return bounding_boxes, face_landmarks_5, face_scores


def detect_with_scrfd(vision_frame : VisionFrame, face_detector_size : str) -> Tuple[List[BoundingBox], List[FaceLandmark5], List[Score]]:
	face_detector = get_face_analyser().get('face_detectors').get('scrfd')
	face_detector_width, face_detector_height = unpack_resolution(face_detector_size)
	temp_vision_frame = resize_frame_resolution(vision_frame, (face_detector_width, face_detector_height))
	ratio_height = vision_frame.shape[0] / temp_vision_frame.shape[0]
	ratio_width = vision_frame.shape[1] / temp_vision_frame.shape[1]
	feature_strides = [ 8, 16, 32 ]
	feature_map_channel = 3
	anchor_total = 2
	bounding_boxes = []
	face_landmarks_5 = []
	face_scores = []

	detect_vision_frame = prepare_detect_frame(temp_vision_frame, face_detector_size)
	with thread_semaphore():
		detections = face_detector.run(None,
		{
			face_detector.get_inputs()[0].name: detect_vision_frame
		})

	for index, feature_stride in enumerate(feature_strides):
		keep_indices = numpy.where(detections[index] >= state_manager.get_item('face_detector_score'))[0]
		if numpy.any(keep_indices):
			stride_height = face_detector_height // feature_stride
			stride_width = face_detector_width // feature_stride
			anchors = create_static_anchors(feature_stride, anchor_total, stride_height, stride_width)
			bounding_box_raw = detections[index + feature_map_channel] * feature_stride
			face_landmark_5_raw = detections[index + feature_map_channel * 2] * feature_stride
			for bounding_box in distance_to_bounding_box(anchors, bounding_box_raw)[keep_indices]:
				bounding_boxes.append(numpy.array(
				[
					bounding_box[0] * ratio_width,
					bounding_box[1] * ratio_height,
					bounding_box[2] * ratio_width,
					bounding_box[3] * ratio_height,
				]))
			for face_landmark_5 in distance_to_face_landmark_5(anchors, face_landmark_5_raw)[keep_indices]:
				face_landmarks_5.append(face_landmark_5 * [ ratio_width, ratio_height ])
			for score in detections[index][keep_indices]:
				face_scores.append(score[0])
	return bounding_boxes, face_landmarks_5, face_scores


def detect_with_yoloface(vision_frame : VisionFrame, face_detector_size : str) -> Tuple[List[BoundingBox], List[FaceLandmark5], List[Score]]:
	face_detector = get_face_analyser().get('face_detectors').get('yoloface')
	face_detector_width, face_detector_height = unpack_resolution(face_detector_size)
	temp_vision_frame = resize_frame_resolution(vision_frame, (face_detector_width, face_detector_height))
	ratio_height = vision_frame.shape[0] / temp_vision_frame.shape[0]
	ratio_width = vision_frame.shape[1] / temp_vision_frame.shape[1]
	bounding_boxes = []
	face_landmarks_5 = []
	face_scores = []

	detect_vision_frame = prepare_detect_frame(temp_vision_frame, face_detector_size)
	with thread_semaphore():
		detections = face_detector.run(None,
		{
			face_detector.get_inputs()[0].name: detect_vision_frame
		})

	detections = numpy.squeeze(detections).T
	bounding_box_raw, score_raw, face_landmark_5_raw = numpy.split(detections, [ 4, 5 ], axis = 1)
	keep_indices = numpy.where(score_raw > state_manager.get_item('face_detector_score'))[0]
	if numpy.any(keep_indices):
		bounding_box_raw, face_landmark_5_raw, score_raw = bounding_box_raw[keep_indices], face_landmark_5_raw[keep_indices], score_raw[keep_indices]
		for bounding_box in bounding_box_raw:
			bounding_boxes.append(numpy.array(
			[
				(bounding_box[0] - bounding_box[2] / 2) * ratio_width,
				(bounding_box[1] - bounding_box[3] / 2) * ratio_height,
				(bounding_box[0] + bounding_box[2] / 2) * ratio_width,
				(bounding_box[1] + bounding_box[3] / 2) * ratio_height,
			]))
		face_landmark_5_raw[:, 0::3] = (face_landmark_5_raw[:, 0::3]) * ratio_width
		face_landmark_5_raw[:, 1::3] = (face_landmark_5_raw[:, 1::3]) * ratio_height
		for face_landmark_5 in face_landmark_5_raw:
			face_landmarks_5.append(numpy.array(face_landmark_5.reshape(-1, 3)[:, :2]))
		face_scores = score_raw.ravel().tolist()
	return bounding_boxes, face_landmarks_5, face_scores


def detect_faces(vision_frame: VisionFrame) -> Tuple[List[BoundingBox], List[FaceLandmark5], List[Score]]:
	bounding_boxes = []
	face_landmarks_5 = []
	face_scores = []

	if state_manager.get_item('face_detector_model') in [ 'many', 'retinaface' ]:
		bounding_boxes_retinaface, face_landmarks_5_retinaface, face_scores_retinaface = detect_with_retinaface(vision_frame, state_manager.get_item('face_detector_size'))
		bounding_boxes.extend(bounding_boxes_retinaface)
		face_landmarks_5.extend(face_landmarks_5_retinaface)
		face_scores.extend(face_scores_retinaface)
	if state_manager.get_item('face_detector_model') in [ 'many', 'scrfd' ]:
		bounding_boxes_scrfd, face_landmarks_5_scrfd, face_scores_scrfd = detect_with_scrfd(vision_frame, state_manager.get_item('face_detector_size'))
		bounding_boxes.extend(bounding_boxes_scrfd)
		face_landmarks_5.extend(face_landmarks_5_scrfd)
		face_scores.extend(face_scores_scrfd)
	if state_manager.get_item('face_detector_model') in [ 'many', 'yoloface' ]:
		bounding_boxes_yoloface, face_landmarks_5_yoloface, face_scores_yoloface = detect_with_yoloface(vision_frame, state_manager.get_item('face_detector_size'))
		bounding_boxes.extend(bounding_boxes_yoloface)
		face_landmarks_5.extend(face_landmarks_5_yoloface)
		face_scores.extend(face_scores_yoloface)
	bounding_boxes = [ normalize_bounding_box(bounding_box) for bounding_box in bounding_boxes ]
	return bounding_boxes, face_landmarks_5, face_scores


def detect_rotated_faces(vision_frame : VisionFrame, angle : Angle) -> Tuple[List[BoundingBox], List[FaceLandmark5], List[Score]]:
	rotated_matrix, rotated_size = create_rotated_matrix_and_size(angle, vision_frame.shape[:2][::-1])
	rotated_vision_frame = cv2.warpAffine(vision_frame, rotated_matrix, rotated_size)
	inverse_rotated_matrix = cv2.invertAffineTransform(rotated_matrix)
	bounding_boxes, face_landmarks_5, face_scores = detect_faces(rotated_vision_frame)
	bounding_boxes = [ transform_bounding_box(bounding_box, inverse_rotated_matrix) for bounding_box in bounding_boxes ]
	face_landmarks_5 = [ transform_points(face_landmark_5, inverse_rotated_matrix) for face_landmark_5 in face_landmarks_5 ]
	return bounding_boxes, face_landmarks_5, face_scores


def prepare_detect_frame(temp_vision_frame : VisionFrame, face_detector_size : str) -> VisionFrame:
	face_detector_width, face_detector_height = unpack_resolution(face_detector_size)
	detect_vision_frame = numpy.zeros((face_detector_height, face_detector_width, 3))
	detect_vision_frame[:temp_vision_frame.shape[0], :temp_vision_frame.shape[1], :] = temp_vision_frame
	detect_vision_frame = (detect_vision_frame - 127.5) / 128.0
	detect_vision_frame = numpy.expand_dims(detect_vision_frame.transpose(2, 0, 1), axis = 0).astype(numpy.float32)
	return detect_vision_frame


def create_faces(vision_frame : VisionFrame, bounding_boxes : List[BoundingBox], face_landmarks_5 : List[FaceLandmark5], face_scores : List[Score]) -> List[Face]:
	faces = []
	nms_threshold = get_nms_threshold(state_manager.get_item('face_detector_model'), state_manager.get_item('face_detector_angles'))
	keep_indices = apply_nms(bounding_boxes, face_scores, state_manager.get_item('face_detector_score'), nms_threshold)

	for index in keep_indices:
		bounding_box = bounding_boxes[index]
		face_landmark_5_68 = face_landmarks_5[index]
		face_landmark_68_5 = expand_face_landmark_68_from_5(face_landmark_5_68)
		face_landmark_68 = face_landmark_68_5
		face_landmark_68_score = 0.0
		face_angle = estimate_face_angle_from_face_landmark_68(face_landmark_68_5)
		if state_manager.get_item('face_landmarker_score') > 0:
			face_landmark_68, face_landmark_68_score = detect_face_landmark_68(vision_frame, bounding_box, face_angle)
			if face_landmark_68_score > state_manager.get_item('face_landmarker_score'):
				face_landmark_5_68 = convert_to_face_landmark_5(face_landmark_68)
		face_landmark_set : FaceLandmarkSet =\
		{
			'5': face_landmarks_5[index],
			'5/68': face_landmark_5_68,
			'68': face_landmark_68,
			'68/5': face_landmark_68_5
		}
		face_score_set : FaceScoreSet =\
		{
			'detector': face_scores[index],
			'landmarker': face_landmark_68_score
		}
		embedding, normed_embedding = calc_embedding(vision_frame, face_landmark_set.get('5/68'))
		gender, age = detect_gender_age(vision_frame, bounding_box)
		faces.append(Face(
			bounding_box = bounding_box,
			landmark_set = face_landmark_set,
			score_set = face_score_set,
			angle = face_angle,
			embedding = embedding,
			normed_embedding = normed_embedding,
			gender = gender,
			age = age
		))
	return faces


def calc_embedding(temp_vision_frame : VisionFrame, face_landmark_5 : FaceLandmark5) -> Tuple[Embedding, Embedding]:
	face_recognizer = get_face_analyser().get('face_recognizer')
	crop_vision_frame, matrix = warp_face_by_face_landmark_5(temp_vision_frame, face_landmark_5, 'arcface_112_v2', (112, 112))
	crop_vision_frame = crop_vision_frame / 127.5 - 1
	crop_vision_frame = crop_vision_frame[:, :, ::-1].transpose(2, 0, 1).astype(numpy.float32)
	crop_vision_frame = numpy.expand_dims(crop_vision_frame, axis = 0)

	with conditional_thread_semaphore():
		embedding = face_recognizer.run(None,
		{
			face_recognizer.get_inputs()[0].name: crop_vision_frame
		})[0]

	embedding = embedding.ravel()
	normed_embedding = embedding / numpy.linalg.norm(embedding)
	return embedding, normed_embedding


def detect_face_landmark_68(temp_vision_frame : VisionFrame, bounding_box : BoundingBox, face_angle : Angle) -> Tuple[FaceLandmark68, Score]:
	face_landmarker = get_face_analyser().get('face_landmarkers').get('68')
	scale = 195 / numpy.subtract(bounding_box[2:], bounding_box[:2]).max().clip(1, None)
	translation = (256 - numpy.add(bounding_box[2:], bounding_box[:2]) * scale) * 0.5
	rotated_matrix, rotated_size = create_rotated_matrix_and_size(face_angle, (256, 256))
	crop_vision_frame, affine_matrix = warp_face_by_translation(temp_vision_frame, translation, scale, (256, 256))
	crop_vision_frame = cv2.warpAffine(crop_vision_frame, rotated_matrix, rotated_size)
	crop_vision_frame = cv2.cvtColor(crop_vision_frame, cv2.COLOR_RGB2Lab)
	if numpy.mean(crop_vision_frame[:, :, 0]) < 30: #type:ignore[arg-type]
		crop_vision_frame[:, :, 0] = cv2.createCLAHE(clipLimit = 2).apply(crop_vision_frame[:, :, 0])
	crop_vision_frame = cv2.cvtColor(crop_vision_frame, cv2.COLOR_Lab2RGB)
	crop_vision_frame = crop_vision_frame.transpose(2, 0, 1).astype(numpy.float32) / 255.0

	with conditional_thread_semaphore():
		face_landmark_68, face_heatmap = face_landmarker.run(None,
		{
			face_landmarker.get_inputs()[0].name: [ crop_vision_frame ]
		})

	face_landmark_68 = face_landmark_68[:, :, :2][0] / 64 * 256
	face_landmark_68 = transform_points(face_landmark_68, cv2.invertAffineTransform(rotated_matrix))
	face_landmark_68 = transform_points(face_landmark_68, cv2.invertAffineTransform(affine_matrix))
	face_landmark_68_score = numpy.amax(face_heatmap, axis = (2, 3))
	face_landmark_68_score = numpy.mean(face_landmark_68_score)
	return face_landmark_68, face_landmark_68_score


def expand_face_landmark_68_from_5(face_landmark_5 : FaceLandmark5) -> FaceLandmark68:
	face_landmarker = get_face_analyser().get('face_landmarkers').get('68_5')
	affine_matrix = estimate_matrix_by_face_landmark_5(face_landmark_5, 'ffhq_512', (1, 1))
	face_landmark_5 = cv2.transform(face_landmark_5.reshape(1, -1, 2), affine_matrix).reshape(-1, 2)

	with conditional_thread_semaphore():
		face_landmark_68_5 = face_landmarker.run(None,
		{
			face_landmarker.get_inputs()[0].name: [ face_landmark_5 ]
		})[0][0]

	face_landmark_68_5 = cv2.transform(face_landmark_68_5.reshape(1, -1, 2), cv2.invertAffineTransform(affine_matrix)).reshape(-1, 2)
	return face_landmark_68_5


def detect_gender_age(temp_vision_frame : VisionFrame, bounding_box : BoundingBox) -> Tuple[int, int]:
	gender_age = get_face_analyser().get('gender_age')
	bounding_box = bounding_box.reshape(2, -1)
	scale = 64 / numpy.subtract(*bounding_box[::-1]).max()
	translation = 48 - bounding_box.sum(axis = 0) * scale * 0.5
	crop_vision_frame, affine_matrix = warp_face_by_translation(temp_vision_frame, translation, scale, (96, 96))
	crop_vision_frame = crop_vision_frame[:, :, ::-1].transpose(2, 0, 1).astype(numpy.float32)
	crop_vision_frame = numpy.expand_dims(crop_vision_frame, axis = 0)

	with conditional_thread_semaphore():
		prediction = gender_age.run(None,
		{
			gender_age.get_inputs()[0].name: crop_vision_frame
		})[0][0]

	gender = int(numpy.argmax(prediction[:2]))
	age = int(numpy.round(prediction[2] * 100))
	return gender, age


def get_one_face(faces : List[Face], position : int = 0) -> Optional[Face]:
	if faces:
		position = min(position, len(faces) - 1)
		return faces[position]
	return None


def get_average_face(faces : List[Face]) -> Optional[Face]:
	embeddings = []
	normed_embeddings = []

	if faces:
		first_face = get_first(faces)

		for face in faces:
			embeddings.append(face.embedding)
			normed_embeddings.append(face.normed_embedding)

		return Face(
			bounding_box = first_face.bounding_box,
			landmark_set = first_face.landmark_set,
			score_set = first_face.score_set,
			angle = first_face.angle,
			embedding = numpy.mean(embeddings, axis = 0),
			normed_embedding = numpy.mean(normed_embeddings, axis = 0),
			gender = first_face.gender,
			age = first_face.age
		)
	return None


def get_many_faces(vision_frames : List[VisionFrame]) -> List[Face]:
	many_faces : List[Face] = []

	for vision_frame in vision_frames:
		if numpy.any(vision_frame):
			static_faces = get_static_faces(vision_frame)
			if static_faces:
				many_faces.extend(static_faces)
			else:
				all_bounding_boxes = []
				all_face_landmarks_5 = []
				all_face_scores = []

				for face_detector_angle in state_manager.get_item('face_detector_angles'):
					if face_detector_angle == 0:
						bounding_boxes, face_landmarks_5, face_scores = detect_faces(vision_frame)
					else:
						bounding_boxes, face_landmarks_5, face_scores = detect_rotated_faces(vision_frame, face_detector_angle)
					all_bounding_boxes.extend(bounding_boxes)
					all_face_landmarks_5.extend(face_landmarks_5)
					all_face_scores.extend(face_scores)

				if all_bounding_boxes and all_face_landmarks_5 and all_face_scores and state_manager.get_item('face_detector_score') > 0:
					faces = create_faces(vision_frame, all_bounding_boxes, all_face_landmarks_5, all_face_scores)

					if faces:
						many_faces.extend(faces)
						set_static_faces(vision_frame, faces)
	return many_faces
