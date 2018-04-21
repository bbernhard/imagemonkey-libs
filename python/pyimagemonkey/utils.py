import os
from pyimagemonkey.exceptions import *
from pyimagemonkey.api import *
import logging
import shutil
import subprocess
import shlex
import logging
import pip
import sys
import enum
import tensorflow as tf
import dataset_util
from PIL import Image
import io
import pyimagemonkey.tf_pipeline_configs as tf_pipeline_configs


def _group_annotations_per_label(annotations):
	result = {}
	for annotation in annotations:
		try:
			annos = result[annotation.label]
			annos.append(annotation)
			result[annotation.label] = annos
		except KeyError:
			result[annotation.label] = [annotation]

	return result

class Type(enum.Enum):
	OBJECT_DETECTION = 0
	IMAGE_CLASSIFICATION = 1

class ProductType(enum.Enum):
	TENSORFLOW = 0
	TENSORFLOW_MODELS = 1



log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())

class TensorflowTrainer(object):
	def __init__(self, training_dir, clear_before_start=False, auto_download_tensorflow_train_script = True, tf_object_detection_models_path = None):
		self._training_dir = training_dir
		self._auto_download_tensorflow_train_script = auto_download_tensorflow_train_script
		self._images_dir = training_dir + os.path.sep + "images"
		self._model_output_dir = training_dir + os.path.sep + "output"
		self._models_dir = training_dir + os.path.sep + "models"
		self._model_output_tmp_dir = self._model_output_dir + os.path.sep + "tmp"
		self._image_classification_output_tmp_dir = self._model_output_tmp_dir + os.path.sep + "image_classification"
		self._object_detection_output_tmp_dir = self._model_output_tmp_dir + os.path.sep + "object_detection"
		self._retrain_py_dir = self._models_dir
		#self._object_detection_py_dir = self._models_dir + os.path.sep + "pyobject_detection"
		self._object_detection_tfrecord_path = self._object_detection_output_tmp_dir  + os.path.sep + "data.tfrecord"
		self._object_detection_label_map_path = self._object_detection_output_tmp_dir  + os.path.sep + "label_map.pbtxt"
		self._object_detection_pipeline_config_path = self._object_detection_output_tmp_dir + os.path.sep + "tf_pipeline.config"
		self._retrain_py = self._retrain_py_dir + os.path.sep + "retrain.py"
		self._tf_object_detection_models_path = tf_object_detection_models_path
		self._api = API(api_version=1)

		if clear_before_start:
			if os.path.exists(self._images_dir):
				self.clear_images_dir()
		else:
			if not self.is_images_dir_empty():
				raise ImageMonkeyGeneralError("training directory %s needs to be empty" %(self._images_dir,)) 

		#create output, output tmp dir and images dir
		if not os.path.exists(self._model_output_dir):
			os.makedirs(self._model_output_dir)

		if not os.path.exists(self._model_output_tmp_dir):
			os.makedirs(self._model_output_tmp_dir)

		if not os.path.exists(self._image_classification_output_tmp_dir):
			os.makedirs(self._image_classification_output_tmp_dir)

		if not os.path.exists(self._object_detection_output_tmp_dir):
			os.makedirs(self._object_detection_output_tmp_dir)

		if not os.path.exists(self._images_dir):
			os.makedirs(self._images_dir)

		if not os.path.exists(self._models_dir):
			os.makedirs(self._models_dir)

		if self._auto_download_tensorflow_train_script:
			if not self._retrain_py_exists():
				installed_tensorflow_version = self._get_installed_tensorflow_version() 
				if installed_tensorflow_version is None:
					raise ImageMonkeyGeneralError("trying to download tensorflow retrain script...couldn't find tenorflow. is it installed?")
				self._download_release_specific_retrain_py(("v" + installed_tensorflow_version))

			#if not self._object_detection_py_exists():
			#	installed_tensorflow_version = self._get_installed_tensorflow_version() 
			#	if installed_tensorflow_version is None:
			#		raise ImageMonkeyGeneralError("trying to download tensorflow object detection scripts...couldn't find tenorflow. is it installed?")
			#	self._download_release_specific_objection_detection_py(("v" + installed_tensorflow_version))


	def _get_installed_tensorflow_version(self):
		installed_packages = pip.get_installed_distributions()
		for i in installed_packages:
			if i.key == "tensorflow":
				return i.version
		return None

	def _get_available_tensorflow_releases(self, product_type=ProductType.TENSORFLOW):
		releases = []
		url = ""
		if product_type == ProductType.TENSORFLOW:
			url = "https://api.github.com/repos/tensorflow/tensorflow/releases"
		elif product_type == ProductType.TENSORFLOW_MODELS:
			url = "https://api.github.com/repos/tensorflow/models/releases"
		else:
			raise ImageMonkeyGeneralError("Invalid Tensorflow Product type")

		resp = requests.get(url)
		if resp.status_code != 200:
			raise ImageMonkeyGeneralError("Couldn't fetch available tensorflow releases")
		data = resp.json()
		for elem in data:
			releases.append(elem["tag_name"])
		return releases

	def _get_commit_hash_for_tensorflow_release(self, release, product_type=ProductType.TENSORFLOW):
		url = ""
		if product_type == ProductType.TENSORFLOW:	
			url = "https://api.github.com/repos/tensorflow/tensorflow/tags"
		elif product_type == ProductType.TENSORFLOW_MODELS:
			url = "https://api.github.com/repos/tensorflow/models/tags"
		else:
			raise ImageMonkeyGeneralError("Invalid Tensorflow Product type")
		resp = requests.get(url)
		if resp.status_code != 200:
			raise ImageMonkeyGeneralError("Couldn't fetch available tensorflow tags")
		data = resp.json()
		for elem in data:
			if elem["name"] == release:
				commit_id = elem["commit"]["sha"] 
				return commit_id
		return None

	def _download_release_specific_retrain_py(self, release):
		releases = self._get_available_tensorflow_releases(product_type=ProductType.TENSORFLOW)
		if release not in releases:
			raise ImageMonkeyGeneralError("'%s' is not a valid tensorflow release" %(release,))
		commit_id = self._get_commit_hash_for_tensorflow_release(release, product_type=ProductType.TENSORFLOW)
		if commit_id is None:
			raise ImageMonkeyGeneralError("fetching tensorflow commit hash...'%s' is not a valid tensorflow release" %(release,))

		#download release specific retrain.py
		url = "https://raw.githubusercontent.com/tensorflow/tensorflow/%s/tensorflow/examples/image_retraining/retrain.py" %(commit_id,)
		resp = requests.get(url)
		if resp.status_code != 200:
			raise ImageMonkeyGeneralError("Couldn't get release specific tensorflow retrain.py")
		with open(self._retrain_py, "wb") as f:
			f.write(resp.content)


	"""def _download_release_specific_objection_detection_py(self, release):
		releases = self._get_available_tensorflow_releases(product_type=ProductType.TENSORFLOW)
		if release not in releases:
			raise ImageMonkeyGeneralError("'%s' is not a valid tensorflow release" %(release,))
		commit_id = self._get_commit_hash_for_tensorflow_release("v.1.6.0", product_type=ProductType.TENSORFLOW_MODELS)
		#commit_id = self._get_commit_hash_for_tensorflow_release(release, product_type=ProductType.TENSORFLOW_MODELS) USE MEEEE
		if commit_id is None:
			raise ImageMonkeyGeneralError("fetching tensorflow commit hash...'%s' is not a valid tensorflow models release" %(release,))

		#download release specific object_detection 
		url = "https://raw.githubusercontent.com/tensorflow/models/%s/object_detection" %(commit_id,)
		print(url)"""



	def clear_images_dir(self):
		for f in os.listdir(self._images_dir):
			filePath = os.path.join(self._images_dir, f)
			try:
				if os.path.isfile(filePath):
					os.unlink(filePath)
				elif os.path.isdir(filePath): shutil.rmtree(filePath)
			except Exception as e:
				log.error("Couldn't clear images directory %s" %(self._images_dir,))
				raise ImageMonkeyGeneralError("Couldn't clear images directory %s" %(self._images_dir,)) 


	def is_images_dir_empty(self):
		if len(os.listdir(self._images_dir)) == 0:
			return True
		return False

	def _create_category_dir(self, category):
		path = self._images_dir + os.path.sep + category
		if os.path.exists(path):
			log.info("Directory %s already exists!" %(path,))
			raise ImageMonkeyGeneralError("Directory %s already exists!" %(path,)) 
		
		os.makedirs(path)

	def _category_dir_exists(self, category):
		path = self._images_dir + os.path.sep + category
		if os.path.exists(path):
			return True
		return False

	def _retrain_py_exists(self):
		if os.path.exists(self._retrain_py):
			return True
		return False

	"""def _object_detection_py_exists(self):
		if os.path.exists(self._object_detection_py_dir):
			return True
		return False"""


	def _run_command(self, command, cwd=None, env=None):
		process = None
		if cwd is None:
			process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, universal_newlines=True)
		else:
			if env is None:
				process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, universal_newlines=True, cwd=cwd)
			else:
				process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, universal_newlines=True, cwd=cwd, env=env)

		for line in iter(process.stderr.readline, b''):
			print(line.rstrip())
			log.info(line.rstrip())

		#for line in iter(process.stdout.readline, b''):
		#	print(line.rstrip())
		#	log.info(line.rstrip())


	def _train_image_classification(self):
		log.debug("Starting tensorflow retrain")
		cmd = ("python " + self._retrain_py + " --image_dir " + self._images_dir + os.path.sep
			+ " --output_graph " + (self._model_output_dir + os.path.sep + "graph.pb") + " --output_labels " + (self._model_output_dir + os.path.sep + "labels.txt")
			+ " --intermediate_output_graphs_dir " + self._image_classification_output_tmp_dir + " --model_dir " + self._models_dir
			+ " --bottleneck_dir " + self._image_classification_output_tmp_dir)
		self._run_command(cmd)

	def _export_data_and_download_images(self, labels, min_probability):
		for label in labels:
			if not self._category_dir_exists(label):
				self._create_category_dir(label)

		res = self._api.export(labels, min_probability)
		for elem in res:
			for validation in elem.validations:
				folder = self._images_dir + os.path.sep + validation.label
				self._api.download_image(elem.image.uuid, folder)

		return res


	def train(self, labels, min_probability = 0.8, train_type=Type.IMAGE_CLASSIFICATION):
		if train_type == Type.IMAGE_CLASSIFICATION:
			self._export_data_and_download_images(labels, min_probability)

			self._train_image_classification()
		elif train_type == Type.OBJECT_DETECTION:
			data = self._export_data_and_download_images(labels, min_probability)

			self._train_object_detection(labels, data)


	def _train_object_detection(self, categories, entries):
		self._write_tf_record_file(categories, entries)
		self._write_labels_map(categories)
		self._write_tf_pipeline_config(categories)
		self._start_object_detection()

	def _start_object_detection(self):
		if self._tf_object_detection_models_path is None:
			raise ImageMonkeyGeneralError("Please provide the base path to your local tensorflow models directory first")

		object_detection_py = self._tf_object_detection_models_path + os.path.sep + "research" + os.path.sep + "object_detection" + os.path.sep + "train.py" 
		if not os.path.exists(object_detection_py):
			raise ImageMonkeyGeneralError("Couldn't find train.py in %s. Is your tensorflow models base directory correctly set?" %(object_detection_py,))

		log.debug("Starting tensorflow object detection training")

		#add tensorflow models to Python path
		my_env = os.environ.copy()
		my_env["PYTHONPATH"] = ((self._tf_object_detection_models_path + os.path.sep + "research") + os.pathsep 
								+ (self._tf_object_detection_models_path + os.path.sep + "research" + os.path.sep + "slim"))


		cmd = ("python " + object_detection_py + " --pipeline_config_path=" + self._object_detection_pipeline_config_path 
				+ " --train_dir=" + self._object_detection_output_tmp_dir)
		self._run_command(cmd, cwd=self._object_detection_output_tmp_dir, env=my_env)


	def _write_tf_pipeline_config(self, categories):
		with open(self._object_detection_pipeline_config_path, "w") as f:
			cfg = tf_pipeline_configs.SSD_MOBILENET_V1
			cfg = cfg.replace("num_classes: xxx", "num_classes: %d" %(len(categories)))
			f.write(cfg)
		


	def _write_tf_record_file(self, categories, entries):
		writer = tf.python_io.TFRecordWriter(self._object_detection_tfrecord_path)
		for entry in entries:
			grouped_annotations = _group_annotations_per_label(entry.annotations)
			for key, annotations in grouped_annotations.items():
				path = self._images_dir + os.path.sep + key + os.path.sep + entry.image.uuid + ".jpg"
				img = Image.open(path).convert('RGB')
				tfrecord = self._create_tf_entry(categories, img, key, entry.image.uuid, annotations)
				if tfrecord is not None:
					writer.write(tfrecord.SerializeToString())
		writer.close()

	def _create_tf_entry(self, categories, img, label, filename, annotations):
		imageFormat = b'jpg'

		width, height = img.size

		imgByteArr = io.BytesIO()
		img.save(imgByteArr, format='JPEG')
		encodedImageData = imgByteArr.getvalue()

		xmins = []
		xmaxs = []
		ymins = []
		ymaxs = []

		for annotation in annotations:
			rect = None
			if type(annotation) is Rectangle: #currently we only support Rect annotations, TODO: change me
				rect = annotation
			elif type(annotation) is Polygon:
				rect = annotation.rect


			if rect is not None:
				scaled_rect = rect.scaled(Rectangle(0, 0, width, height)) #scale to image dimension in case annotation exceeds image width/height

				xmin = scaled_rect.left / float(width)
				xmax = (scaled_rect.left + scaled_rect.width) / float(width)
				ymin = scaled_rect.top / float(height)
				ymax = (scaled_rect.top + scaled_rect.height) / float(height)

				xmins.append(xmin)
				xmaxs.append(xmax)
				ymins.append(ymin)
				ymaxs.append(ymax)



		#we might have some images in our dataset, which don't have a annotation, skip those
		if((len(xmins) == 0) or (len(xmaxs) == 0) or (len(ymins) == 0) or (len(ymaxs) == 0)):
			return None

		#xmins.append(10)
		#ymins.append(10)
		#xmaxs.append(10)
		#ymaxs.append(10)
 
		classes = [(categories.index(label) + 1)] #class indexes start with 1

		tf_example = tf.train.Example(features=tf.train.Features(feature={
	      'image/height': dataset_util.int64_feature(height),
	      'image/width': dataset_util.int64_feature(width),
	      'image/filename': dataset_util.bytes_feature(filename.encode()),
	      'image/source_id': dataset_util.bytes_feature(filename.encode()),
	      'image/encoded': dataset_util.bytes_feature(encodedImageData),
	      'image/format': dataset_util.bytes_feature(imageFormat),
	      'image/object/bbox/xmin': dataset_util.float_list_feature(xmins),
	      'image/object/bbox/xmax': dataset_util.float_list_feature(xmaxs),
	      'image/object/bbox/ymin': dataset_util.float_list_feature(ymins),
	      'image/object/bbox/ymax': dataset_util.float_list_feature(ymaxs),
	      'image/object/class/text': dataset_util.bytes_list_feature([label.encode('utf8')]),
	      'image/object/class/label': dataset_util.int64_list_feature(classes),
		}))
		return tf_example

	def _write_labels_map(self, categories):
		content = ""
		for i in range(len(categories)):
			category = categories[i]
			content += "item {\n   id:  %d\n   name: '%s'\n}\n\n" %((i+1), category) #ids need to start with 1

		with open(self._object_detection_label_map_path, "w") as f:
			f.write(content)





