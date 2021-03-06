import os
import sys
import requests
from PIL import Image
import io
import json
import secrets
import traceback
from six.moves import input as raw_input

FOLDERNAME = ""
BASEURL = 'https://api.imagemonkey.io' #'http://127.0.0.1:8081'

current_dir = os.path.dirname(os.path.abspath(__file__))

if not hasattr(secrets, 'X_API_TOKEN') or secrets.X_API_TOKEN == "":
	print("Please provide a valid API Token in secrets.py")
	sys.exit(1)


def _confirm(files, image_collection, labels):
	print("Are you sure you want to donate these %d images?\n" %(len(files)))

	if image_collection is not None:
		print("##############################################################")
		print("###################### Image Collection ######################")
		print("##############################################################\n\n")
		print(image_collection)

	print("##############################################################")
	print("########################### Labels ###########################")
	print("##############################################################\n\n")
	for elem in labels:
		print("Label: %s\tannotatable: %d" %(elem["label"], elem["annotatable"]))

	print("\n\n##############################################################")
	print("########################### Images ###########################")
	print("##############################################################\n\n")
	for file in files:
		print(path + os.path.sep + file)

	print("\n")
	line = raw_input("Are you sure? [yes/no]\n")
	if line == "yes":
		return True
	return False

def _parse_and_validate_labels_file(path):
	data = None
	with open(path) as f:
		data = json.load(f)

	
	parsed_data = []
	if "labels" in data:
		for idx, item in enumerate(labels):
			if "label" not in item:
				print("Couldn't parse labels file - expected a property 'label' in \n\n\t%s." %(item,))
				sys.exit(1)

			if "annotatable" not in item:
				print("Couldn't parse labels file - expected a property 'annotatable' in\n\n\t%s." %(item,))
				sys.exit(1)

			if type(item["label"]) is not str:
				print("Couldn't parse labels file - property 'label' in\n\n\t%s\nneeds to be of type 'str'.\n\n" %(item,))
				sys.exit(1)

			if type(item["annotatable"]) is not bool:
				print("Couldn't parse labels file - property 'annotatable' in\n\n\t%s\nneeds to be of type 'boolean'.\n\n" %(item,))
				sys.exit(1)

			parsed_data.append(item)

	image_collection = None
	if "image_collection" in data:
		image_collection = data["image_collection"]

	return image_collection, parsed_data


def _add_labels(uuid, labels):
	print("Adding label...")

	url = BASEURL + "/v1/donation/" + uuid + "/labelme"

	l = []
	for elem in labels:
		l.append({"label": elem["label"], "annotatable": elem["annotatable"]})

	try:
		response = requests.post(url, json=l, headers={"X-Api-Token": secrets.X_API_TOKEN})
		if not response.status_code == 200:
			print("Couldn't label %s: failed with status code: %d, error: %s" %(uuid, response.status_code, response.text,))
	except Exception as e:
		traceback.print_exc()
		print("Timeout for %s: " %(uuid,))


def _push(full_path, image_collection, labels):
	url = BASEURL + '/v1/donate?add_sublabels=false'

	img_bytes = None
	try:
		img_bytes = _load_img_and_resize(full_path)
	except ValueError:
		print("Couldn't push image %s - invalid image" %(full_path,))
		return

	multipart_formdata = {
		'image': ('file.jpg', img_bytes, 'image/jpg'),
	}

	formdata = {}
	if image_collection is not None:
		formdata["image_collection"] = image_collection

	print("Pushing: %s" %(full_path,))
	try:
		response = requests.post(url, files=multipart_formdata, data=formdata, headers={"X-Api-Token": secrets.X_API_TOKEN})#, data={'label' : label})
		if not response.status_code == 200:
			print("Couldn't push %s: failed with status code: %d, error: %s" %(f, response.status_code, response.text,))
		else:
			if len(labels) > 0:
				_add_labels(response.json()["uuid"], labels)
	except Exception as e:
		traceback.print_exc()
		print("Timeout for %s: " %(f,))

def _load_img_and_resize(path):
	max_dimension = 1024 #px

	img = Image.open(path)

	#get image's size and scale it
	scale_factor = 1.0
	width, height = img.size
	if width > height:
		scale_factor = max_dimension/width
	else:
		scale_factor = max_dimension/height

	if scale_factor > 1.0:
		scale_factor = 1.0

	new_width = round(width * scale_factor)
	new_height = round(height * scale_factor)


	#get binary representation
	img = img.resize((int(new_width), int(new_height)), Image.ANTIALIAS)

	output = io.BytesIO()
	img.save(output, format='JPEG')
	return output.getvalue()


if __name__ == "__main__":
	if FOLDERNAME == "":
		print("Please provide a valid foldername!")
		sys.exit(1)

	path = current_dir + os.path.sep + FOLDERNAME
	if not os.path.exists(path):
		print("Folder '%s' does not exist!" %(path,))
		sys.exit(1)

	labels_file_path = path + ".json"
	if not os.path.exists(labels_file_path):
		print("Labels file %s does not exist!" %(labels_file_path,))
		sys.exit(1)

	image_collection, labels = _parse_and_validate_labels_file(labels_file_path)

	files = os.listdir(path)

	if not _confirm(files, image_collection, labels):
		print("aborted due to user input")
		sys.exit(1)

	for f in files:
		full_path = path + os.path.sep + f
		_push(full_path, image_collection, labels)