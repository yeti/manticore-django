import StringIO
import os
from PIL import Image
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.db import models
from _ssl import SSLError


class CoreModel(models.Model):
    created = models.DateTimeField(auto_now_add=True, null=True)

    def __repr__(self):
        return '<%s:%s %s>' % (self.__class__.__name__, self.pk, str(self))

    class Meta:
        abstract = True


# Requires the model to have one image field called original_photo and a constant called SIZES
def resize_model_photos(sender, **kwargs):
    # Update fields is used when saving the photo so that we can short circuit an infinite loop with the signal
    if not kwargs['update_fields'] or not 'original_photo' in kwargs['update_fields']:
        return

    if not kwargs['instance'].original_photo:
        for size_name, size in sender.SIZES.iteritems():
            setattr(kwargs['instance'], size_name, '')
        return

    processed = process_thumbnail(kwargs['instance'], sender.SIZES)
    if processed:
        kwargs['instance'].save()


def process_thumbnail(instance, sizes, crop=False):
    file = StringIO.StringIO(instance.original_photo.read())
    original_image = Image.open(file)  # open the image using PIL

    # pull a few variables out of that full path
    filename = os.path.basename(instance.original_photo.name).rsplit('.', 1)[0]
    extension = os.path.basename(instance.original_photo.name).rsplit('.', 1)[1]  # the file extension

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

        done, tries = False, 0
        while not done:
            try:
                # Make sure we're at the beginning of the file for reading when saving
                temp_file.seek(0)
                getattr(instance, size_name).save(name, temp_file)
                done = True
            except SSLError:
                pass

            # Try at max, 10 times before quitting
            tries += 1
            if tries > 10:
                done = True

    return True