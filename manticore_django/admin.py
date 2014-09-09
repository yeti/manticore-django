from django.contrib import admin


class MediaAdmin(admin.ModelAdmin):
    list_display = ('type', 'original_file', 'thumbnail')
