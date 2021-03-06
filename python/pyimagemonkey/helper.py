import tarfile
import os
import logging
import subprocess
import sys

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())

def is_directory(path):
	return os.path.isdir(path)

def directory_exists(path):
	return (os.path.exists(path) and is_directory(path))

def extract_tar_gz(input_file, output_path):
	#if not is_directory(output_path):
	#	raise ImageMonkeyGeneralError("%s is not a directory" %(output_path,)) 

	tar = tarfile.open(input_file, "r:gz")
	tar.extractall(path=output_path)
	tar.close()


def clear_output_dir(output_dir):
        for f in os.listdir(output_dir):
                filePath = os.path.join(output_dir, f)
                try:
                        if os.path.isfile(filePath):
                                os.unlink(filePath)
                        elif os.path.isdir(filePath): shutil.rmtree(filePath)
                except Exception as e:
                        log.error("Couldn't clear output directory %s" %(output_dir,))
                        raise ImageMonkeyGeneralError("Couldn't clear output directory %s" %(output_dir,))


def run_command(command, cwd=None, env=None):
        process = None
        if cwd is None:
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=sys.stdout, universal_newlines=True)
        else:
                if env is None:
                        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=sys.stdout, universal_newlines=True, cwd=cwd)
                else:
                        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=sys.stdout, universal_newlines=True, cwd=cwd, env=env)

        for line in iter(process.stdout.readline, b''):
                print(line.rstrip())
                log.info(line.rstrip())
                if process.poll() is not None:
                        return
