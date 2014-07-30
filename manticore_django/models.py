import StringIO
import os
from PIL import Image
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.db import models
from manticore_django.manticore_django.utils import retry_cloudfiles


class CoreModel(models.Model):
    created = models.DateTimeField(auto_now_add=True, null=True)

    def __repr__(self):
        return '<%s:%s %s>' % (self.__class__.__name__, self.pk, str(self))

    class Meta:
        abstract = True


# Requires the model to have one field to hold the original file and a constant called SIZES
def resize_model_photos(sender, **kwargs):
    instance = kwargs['instance']
    original_file_field_name = getattr(sender, "_original_file", "original_file")

    # If this is a video file, do nothing
    file_type = getattr(instance, "type", None)
    if file_type:
        if file_type == sender.TYPE_CHOICES.video:
            return

    # Update fields is used when saving the photo so that we can short circuit an infinite loop with the signal
    if not kwargs['update_fields'] or not original_file_field_name in kwargs['update_fields']:
        return

    original_file = getattr(instance, original_file_field_name)
    if not original_file:
        for size_name, size in sender.SIZES.iteritems():
            setattr(instance, size_name, '')
        return

    processed = process_thumbnail(instance, original_file, sender.SIZES)
    if processed:
        instance.save()


def process_thumbnail(instance, original_file, sizes, crop=False):
    file = StringIO.StringIO(original_file.read())
    original_image = Image.open(file)  # open the image using PIL

    # pull a few variables out of that full path
    filename = os.path.basename(original_file.name).rsplit('.', 1)[0]
    extension = os.path.basename(original_file.name).rsplit('.', 1)[1]  # the file extension

    # If there is no extension found try jpg
    if extension == '':
        extension = 'jpg'

    # use the file extension to determine if the image is valid before proceeding
    if extension not in ['jpg', 'jpeg', 'gif', 'png']:
        return False

    for size_name, size in sizes.iteritems():
        im = original_image.copy()

        (x_size, y_size) = im.size
        original_ratio = float(x_size) / float(y_size)
        width = size['width']
        height = size['height']
        new_ratio = float(width / height)
        if new_ratio > original_ratio:
            im = im.resize((width, int(width / original_ratio)), Image.ANTIALIAS)
            if crop:
                clip_amount = int((int(width / original_ratio) - height) / 2)
                im = im.crop((0, clip_amount, width,height + clip_amount))
        else:
            im = im.resize((int(height * original_ratio), height), Image.ANTIALIAS)
            if crop:
                clip_amount = int((int(height * original_ratio) - width) / 2)
                im = im.crop((clip_amount, 0, width + clip_amount, height))

        name = "%s.jpg" % filename
        tempfile_io = StringIO.StringIO()
        if im.mode != "RGB":
            im = im.convert("RGB")
        im.save(tempfile_io, 'JPEG')

        temp_file = InMemoryUploadedFile(tempfile_io, None, name, 'image/jpeg', tempfile_io.len, None)

        def save_image(temp_file, instance, size_name, name):
            # Make sure we're at the beginning of the file for reading when saving
            temp_file.seek(0)
            getattr(instance, size_name).save(name, temp_file)

        retry_cloudfiles(save_image, temp_file, instance, size_name, name)

    return True