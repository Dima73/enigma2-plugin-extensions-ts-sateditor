from distutils.core import setup
import setup_translate


setup(name='enigma2-plugin-extensions-ts-sateditor',
		version='2.4',
		author='Dimitrij',
		author_email='dima-73@inbox.lv',
		package_dir={'SystemPlugins.TSsatEditor': 'src'},
		packages=['SystemPlugins.TSsatEditor'],
		package_data={'SystemPlugins.TSsatEditor': ['*.sh', '*.xml', 'ddbuttons/*.png']},
		description='manage satellites/transponders for user satellites.xml',
		cmdclass=setup_translate.cmdclass,
	)
