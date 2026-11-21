# Build a self-contained AppImage from the host's system Python.
# Bundles Python, its stdlib, the packages the app imports, and their shared libs.
# glibc is not bundled, so the AppImage needs glibc >= the build host's.

APP      := bt_hid_kvm
ARCH     := x86_64
PY_VER   := 3.14
TCL_VER  := 8.6
PYTHON   := /usr/bin/python$(PY_VER)
SYS_LIB  := /usr/lib/$(ARCH)-linux-gnu
SYS_PKG  := /usr/lib/python3/dist-packages

APP_SOURCES := __main__.py components constants utils
# gi imports cairo on load
PY_PACKAGES := evdev dbus gi cairo _dbus_bindings.cpython-* _dbus_glib_bindings.cpython-*
# Loaded by `from gi.repository import GLib`
TYPELIBS    := GLib-2.0 GLibUnix-2.0
# Must come from the host, or its dynamic loader breaks
GLIBC_LIBS  := /(ld-linux-[^/]*|lib(c|m|dl|pthread|rt|resolv|util|mvec|anl))\.so

BUILD_DIR := build
TOOLS_DIR := $(BUILD_DIR)/tools
APPDIR    := $(BUILD_DIR)/AppDir
APPIMAGE  := dist/BT_HID_KVM-$(ARCH).AppImage
PKG_DIR   := $(APPDIR)/usr/lib/python3/dist-packages

APPIMAGETOOL     := $(TOOLS_DIR)/appimagetool-1.9.1-$(ARCH).AppImage
APPIMAGETOOL_URL := https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-$(ARCH).AppImage
APPIMAGETOOL_SHA := ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0
RUNTIME          := $(TOOLS_DIR)/runtime-20251108-$(ARCH)
RUNTIME_URL      := https://github.com/AppImage/type2-runtime/releases/download/20251108/runtime-$(ARCH)
RUNTIME_SHA      := 2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d

# $(call download,url,sha256)
download = mkdir -p $(@D) && curl -fsSLo $@.part $(1) && echo '$(2)  $@.part' | sha256sum -c --quiet - && mv $@.part $@

# Plain `make` builds the AppImage.
.DEFAULT_GOAL := appimage

.PHONY: appimage clean

appimage: $(APPIMAGETOOL) $(RUNTIME)
	rm -rf $(APPDIR)
	mkdir -p $(APPDIR)/usr/bin $(PKG_DIR)/$(APP) $(APPDIR)/usr/lib/girepository-1.0 $(APPDIR)/usr/share/tcltk dist
	cp -a $(PYTHON) $(APPDIR)/usr/bin/python3
	cp -a /usr/lib/python$(PY_VER) $(APPDIR)/usr/lib/
	cd $(APPDIR)/usr/lib/python$(PY_VER) && rm -rf config-$(PY_VER)-* dist-packages sitecustomize.py
	cd $(SYS_PKG) && cp -a $(PY_PACKAGES) $(CURDIR)/$(PKG_DIR)/
	# App uses the GLib main loop; the Qt one pulls in Qt6 + ICU (~45MB)
	rm -f $(PKG_DIR)/dbus/mainloop/pyqt6*.so
	tar -cf - --exclude=__tests__ --exclude=__pycache__ $(APP_SOURCES) | tar -xf - -C $(PKG_DIR)/$(APP)
	cp -a $(foreach t,$(TYPELIBS),$(SYS_LIB)/girepository-1.0/$(t).typelib) $(APPDIR)/usr/lib/girepository-1.0/
	cp -a /usr/share/tcltk/tcl$(TCL_VER) /usr/share/tcltk/tk$(TCL_VER) $(APPDIR)/usr/share/tcltk/
	ldd $(APPDIR)/usr/bin/python3 $$(find $(APPDIR)/usr/lib -name '*.so' -type f) \
		| awk '$$2 == "=>" && $$3 ~ /^\// { print $$3 }' | sort -u | grep -Ev '$(GLIBC_LIBS)' \
		| xargs cp -L -t $(APPDIR)/usr/lib/
	cp -a packaging/appimage/AppRun packaging/appimage/$(APP).desktop packaging/appimage/$(APP).svg $(APPDIR)/
	ARCH=$(ARCH) $(APPIMAGETOOL) --runtime-file $(RUNTIME) $(APPDIR) $(APPIMAGE)

$(APPIMAGETOOL):
	$(call download,$(APPIMAGETOOL_URL),$(APPIMAGETOOL_SHA))
	chmod +x $@

$(RUNTIME):
	$(call download,$(RUNTIME_URL),$(RUNTIME_SHA))

clean:
	rm -rf $(BUILD_DIR) dist
