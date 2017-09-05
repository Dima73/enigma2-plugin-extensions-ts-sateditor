from distutils.core import setup
import setup_translate


setup(name = 'enigma2-plugin-extensions-ts-sateditor',
		version='2.4',
		author='Dimitrij',
		author_email='dima-73@inbox.lv',
		package_dir = {'Extensions.TSsatEditor': 'src'},
		packages=['Extensions.TSsatEditor'],
		package_data={'Extensions.TSsatEditor': ['*.sh', '*.xml', 'ddbuttons/*.png']},
		description = 'manage satellites/transponders for user satellites.xml',
		cmdclass = setup_translate.cmdclass,
	)

