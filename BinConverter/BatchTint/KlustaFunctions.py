# import os, read_data, json, subprocess
import os, json, subprocess, time, datetime, queue, threading, smtplib
from PyQt4 import QtGui
# from PyQt5 import QtGui
# from multiprocessing.dummy import Pool as ThreadPool
# from email.mime.text import MIMEText


def is_tetrode(file, session):

    if os.path.splitext(file)[0] == session:
        try:
            tetrode_number = int(os.path.splitext(file)[1][1:])
            return True
        except ValueError:
            return False
    else:
        return False


def get_tetrode_files(file_list, session):
    tetrode_files = [file for file in file_list if is_tetrode(file, session)]
    return tetrode_files


def klusta(self, sub_directory, directory, settings_fname):

    self.LogAppend.myGUI_signal.emit(
        '[%s %s]: Now analyzing files in the %s folder!' % (
            str(datetime.datetime.now().date()),
            str(datetime.datetime.now().time())[
            :8], sub_directory))
    
    sub_directory_fullpath = os.path.join(directory, sub_directory)  # defines fullpath

    logfile_directory = os.path.join(sub_directory_fullpath, 'LogFiles')  # defines directory for log files
    inifile_directory = os.path.join(sub_directory_fullpath, 'IniFiles')  # defines directory for .ini files

    processed_directory = os.path.join(directory, 'Processed')  # defines processed file directory

    for _ in [processed_directory, logfile_directory, inifile_directory]:
        if not os.path.exists(_):  # makes the directories if they don't exist
            os.makedirs(_)

    with open(settings_fname, 'r+') as f:  # opens setting file
        self.settings = json.load(f)  # loads settings

    f_list = os.listdir(sub_directory_fullpath)  # finds the files within that directory

    set_files = [file for file in f_list if '.set' in file]  # fines .set files

    if len(set_files) > 1:  # displays messages counting how many set files in directory
        self.LogAppend.myGUI_signal.emit(
            '[%s %s]: There are %d \'.set\' files in this directory!' % (
                str(datetime.datetime.now().date()),
                str(datetime.datetime.now().time())[
                :8], len(set_files)))
    elif len(set_files) == 1:
        self.LogAppend.myGUI_signal.emit(
            '[%s %s]: There is %d \'.set\' file in this directory!' % (
                str(datetime.datetime.now().date()),
                str(datetime.datetime.now().time())[
                :8], len(set_files)))

    skipped = 0
    experimenter = []  # initializing experimenter list
    error = []  # initializing error list
    for i in range(len(set_files)):  # loops through each set file
        set_file = os.path.splitext(set_files[i])[0]  # define set file without extension
        set_path = os.path.join(sub_directory_fullpath, set_file)  # defines set file path

        self.LogAppend.myGUI_signal.emit(
            '[%s %s]: Now analyzing tetrodes associated with the %s \'.set\' file (%d/%d)!' % (
                str(datetime.datetime.now().date()),
                str(datetime.datetime.now().time())[
                :8], set_file, i+1, len(set_files)))

        # acquires tetrode files within directory
        # tet_list = [file for file in f_list if file in ['%s.%d' % (set_file, tet_num)
        #                                                for tet_num in range(1, int(self.settings['NumTet']) + 1)]]

        tet_list = get_tetrode_files(f_list, set_file)
        #  if there are no tetrodes then skips

        analyzeable, error_return = check_analyzeable(self, sub_directory_fullpath, set_file, tet_list)

        if analyzeable:
            q = queue.Queue()
            for u in tet_list:
                q.put(u)

            ThreadCount = int(self.settings['NumThreads'])

            if ThreadCount > len(tet_list):
                ThreadCount = len(tet_list)
            skipped_mat = []

            with open(set_path + '.set', 'r+') as f:
                for line in f:
                    if 'experimenter ' in line:
                        expter_line = line.split(' ', 1)
                        expter_line.remove('experimenter')
                        experimenter.append(' '.join(expter_line))
                        break

            while not q.empty():
                Threads = []
                for i in range(ThreadCount):
                    t = threading.Thread(target=analyze_tetrode, args=(self, q, experimenter, error, skipped_mat,
                                                                       i, set_path, set_file, f_list,
                                                                       sub_directory_fullpath, logfile_directory,
                                                                       inifile_directory))
                    time.sleep(1)
                    t.daemon = True
                    t.start()
                    Threads.append(t)

                # q.join()
                for t in Threads:
                    t.join()
            q.join()
        else:
            error.extend(error_return)
            continue

    self.LogAppend.myGUI_signal.emit(
        '[%s %s]: Analysis in the %s directory has been completed!' % (
            str(datetime.datetime.now().date()),
            str(datetime.datetime.now().time())[
            :8], sub_directory))

    processed_directory = os.path.join(directory, 'Processed')

    processing = 1
    while processing == 1:
        time.sleep(2)
        processing = 0
        try:
            # moves the entire folder to the processed folder
            os.rename(sub_directory_fullpath, os.path.join(processed_directory, sub_directory))
        except PermissionError:
            processing = 1


def analyze_tetrode(self, q, experimenter,
                    error, skipped_mat, index, set_path, set_file, f_list, sub_directory_fullpath,
                    logfile_directory, inifile_directory):
    '''
    self.settings_fname = 'settings.json'

    with open(self.settings_fname, 'r+') as filename:
        self.settings = json.load(filename)
    '''
    # item = q.get()

    inactive_tet_dir = os.path.join(sub_directory_fullpath, 'InactiveTetrodeFiles')
    no_spike_dir = os.path.join(sub_directory_fullpath, 'NoSpikeFiles')

    if q.empty():
        try:
            q.task_done()
        except ValueError:
            pass
    else:
        tet_list = [q.get()]
        for tet_fname in tet_list:

            '''
            for i in range(1, int(self.settings['NumTet']) + 1):
                if ['%s%d' % ('.', i) in tet_fname][0]:
                    tetrode = i
            '''

            tetrode = int(os.path.splitext(tet_fname)[-1][1:])

            self.LogAppend.myGUI_signal.emit(
                '[%s %s]: Now analyzing the following file: %s!' % (
                    str(datetime.datetime.now().date()),
                    str(datetime.datetime.now().time())[
                    :8], tet_fname))

            clu_name = set_path + '.clu.' + str(tetrode)
            cut_path = set_path + '_' + str(tetrode) + '.cut'
            cut_name = set_file + '_' + str(tetrode) + '.cut'

            if cut_name in f_list:
                self.LogAppend.myGUI_signal.emit(
                    '[%s %s]: The %s file has already been analyzed!' % (
                        str(datetime.datetime.now().date()),
                        str(datetime.datetime.now().time())[
                        :8], tet_fname))

                q.task_done()
                continue

            tet_path = os.path.join(sub_directory_fullpath, tet_fname)

            ini_fpath = tet_path + '.ini'  # .ini filename
            ini_fname = tet_fname + '.ini'  # .ini fullpath

            parm_space = ' '
            # klusta kwik parameters to utilize
            kkparmstr = parm_space.join(['-MaxPossibleClusters', str(self.settings['MaxPos']),
                                         '-UseFeatures', str(self.settings['UseFeatures']),
                                         '-nStarts', str(self.settings['nStarts']),
                                         '-RandomSeed', str(self.settings['RandomSeed']),
                                         '-DistThresh', str(self.settings['DistThresh']),
                                         '-FullStepEvery', str(self.settings['FullStepEvery']),
                                         '-ChangedThresh', str(self.settings['ChangedThresh']),
                                         '-MaxIter', str(self.settings['MaxIter']),
                                         '-SplitEvery', str(self.settings['SplitEvery']),
                                         '-Subset', str(self.settings['Subset']),
                                         '-PenaltyK', str(self.settings['PenaltyK']),
                                         '-PenaltyKLogN', str(self.settings['PenaltyKLogN']),
                                         '-UseDistributional', '1',
                                         '-UseMaskedInitialConditions', '1',
                                         '-AssignToFirstClosestMask', '1',
                                         '-PriorPoint', '1',
                                         ])

            s = "\n"
            # channels to include
            inc_channels = s.join(['[IncludeChannels]',
                                   '1=' + str(self.settings['1']),
                                   '2=' + str(self.settings['2']),
                                   '3=' + str(self.settings['3']),
                                   '4=' + str(self.settings['4'])
                                   ])
            # write these settings to the .ini file
            with open(ini_fpath, 'w') as fname:

                s = "\n"
                main_seq = s.join(['[Main]',
                                   str('Filename=' + '"' + set_path + '"'),
                                   str('IDnumber=' + str(tetrode)),
                                   str('KKparamstr=' + kkparmstr),
                                   str(inc_channels)
                                   ])

                clust_ft_seq = s.join(['\n[ClusteringFeatures]',
                                       str('PC1=' + str(self.settings['PC1'])),
                                       str('PC2=' + str(self.settings['PC2'])),
                                       str('PC3=' + str(self.settings['PC3'])),
                                       str('PC4=' + str(self.settings['PC4'])),
                                       str('A=' + str(self.settings['A'])),
                                       str('Vt=' + str(self.settings['Vt'])),
                                       str('P=' + str(self.settings['P'])),
                                       str('T=' + str(self.settings['T'])),
                                       str('tP=' + str(self.settings['tP'])),
                                       str('tT=' + str(self.settings['tT'])),
                                       str('En=' + str(self.settings['En'])),
                                       str('Ar=' + str(self.settings['Ar']))
                                       ])

                report_seq = s.join(['\n[Reporting]',
                                     'Log=' + str(self.settings['Log File']),
                                     'Verbose=' + str(self.settings['Verbose']),
                                     'Screen=' + str(self.settings['Screen'])
                                     ])

                for write_order in [main_seq, clust_ft_seq, report_seq]:
                    fname.seek(0, 2)  # seek the files end
                    fname.write(write_order)
                fname.close()


            log_fpath = tet_path + '_log.txt'
            log_fname = tet_fname + '_log.txt'

            cmdline = ["cmd", "/q", "/k", "echo off"]
            reading = 1
            with open(tet_path, 'rb') as f:
                while reading == 1:
                    line = f.readline()
                    if 'experimenter ' in str(line):
                        expter_line = str(line).split(' ', 1)
                        expter_line.remove("b'experimenter")
                        experimenter.append(' '.join(expter_line))
                        reading = 0
                    elif 'data_start' in str(line):
                        reading = 0

            #time.sleep(2)
            cmd = subprocess.Popen(cmdline, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
            if self.settings['Silent'] == 0:
                batch = bytes(
                    'tint ' + '"' + set_path + '" ' + str(
                        tetrode) + ' "' + log_fpath + '" /runKK /KKoptions "' +
                    ini_fpath + '" /convertkk2cut /visible\n'
                    'exit\n', 'ascii')
            else:
                batch = bytes(
                    'tint ' + '"' + set_path + '" ' + str(
                        tetrode) + ' "' + log_fpath + '" /runKK /KKoptions "' +
                    ini_fpath + '" /convertkk2cut\n'
                                'exit\n', 'ascii')

            cmd.stdin.write(batch)
            cmd.stdin.flush()

            processing = 1

            while processing == 1:
                time.sleep(2)
                new_cont = os.listdir(sub_directory_fullpath)

                if cut_name in new_cont:
                    processing = 0
                    try:
                        try:
                            # moves the log files
                            try:
                                os.rename(log_fpath, os.path.join(logfile_directory, tet_fname + '_log.txt'))
                            except FileNotFoundError:
                                pass

                        except FileExistsError:
                            os.remove(os.path.join(logfile_directory, tet_fname + '_log.txt'))
                            os.rename(log_fpath, os.path.join(logfile_directory, tet_fname + '_log.txt'))
                        try:
                            # moves the .ini files
                            os.rename(ini_fpath, os.path.join(inifile_directory, tet_fname + '.ini'))
                        except FileExistsError:
                            os.remove(os.path.join(inifile_directory, tet_fname + '.ini'))
                            os.rename(ini_fpath, os.path.join(inifile_directory, tet_fname + '.ini'))

                        self.LogAppend.myGUI_signal.emit(
                            '[%s %s]: The analysis of the %s file has finished!' % (
                                str(datetime.datetime.now().date()),
                                str(datetime.datetime.now().time())[
                                :8], tet_fname))
                        pass

                    except PermissionError:
                        processing = 1

                elif log_fname in new_cont:
                    active_tet = []
                    no_spike = []
                    with open(log_fpath, 'r') as f:
                        for line in f:
                            if 'list of active tetrodes:' in line:
                                activ_tet = line
                                if str(tetrode) not in str(line):

                                    if not os.path.exists(inactive_tet_dir):
                                        os.makedirs(inactive_tet_dir)

                                    cur_date = datetime.datetime.now().date()
                                    cur_time = datetime.datetime.now().time()
                                    not_active = ': Tetrode ' + str(tetrode) + ' is not active within the ' + \
                                                 set_file + ' set file!'
                                    error.append('\tTetrode ' + str(tetrode) + ' was not active within the ' + \
                                                 set_file + ' \'.set\' file, couldn\'t perform analysis.\n')
                                    print('[' + str(cur_date) + ' ' + str(cur_time)[:8] + ']' + not_active)
                                    break
                            elif 'reading 0 spikes' in line:

                                if not os.path.exists(no_spike_dir):
                                    os.makedirs(no_spike_dir)

                                no_spike = 1
                                # skipped_mat.append(1)
                                cur_date = datetime.datetime.now().date()
                                cur_time = datetime.datetime.now().time()
                                not_spike = ': Tetrode ' + str(tetrode) + ' within the ' + \
                                             set_file + ' \'.set\' file, has no spikes, skipping analysis!'

                                error.append('\tTetrode ' + str(tetrode) + ' within the ' + \
                                             set_file + ' \'.set\' file, had no spikes, couldn\'t perform analysis\n')

                                print('[' + str(cur_date) + ' ' + str(cur_time)[:8] + ']' + not_spike)
                                break

                            else:
                                activ_tet = []

                    if 'activ_tet' in locals() and activ_tet != [] and str(tetrode) not in str(activ_tet):
                        x = 1
                        while x == 1:
                            try:
                                try:
                                    # moves the log files
                                    try:
                                        os.rename(log_fpath,
                                                  os.path.join(logfile_directory, tet_fname + '_log.txt'))
                                    except FileNotFoundError:
                                        pass

                                except FileExistsError:
                                    os.remove(os.path.join(logfile_directory, tet_fname + '_log.txt'))
                                    os.rename(log_fpath,
                                              os.path.join(logfile_directory, tet_fname + '_log.txt'))
                                try:
                                    # moves the .ini files
                                    os.rename(ini_fpath, os.path.join(inifile_directory, tet_fname + '.ini'))
                                except FileExistsError:
                                    os.remove(os.path.join(inifile_directory, tet_fname + '.ini'))
                                    os.rename(ini_fpath, os.path.join(inifile_directory, tet_fname + '.ini'))

                                os.rename(tet_path, os.path.join(inactive_tet_dir, tet_fname))

                                x = 0

                            except PermissionError:
                                x = 1
                            processing = 0

                    if 'no_spike' in locals() and no_spike == 1:
                        x = 1
                        while x == 1:
                            try:
                                try:
                                    # moves the log files
                                    try:
                                        os.rename(log_fpath,
                                                  os.path.join(logfile_directory, tet_fname + '_log.txt'))
                                    except FileNotFoundError:
                                        pass

                                except FileExistsError:
                                    os.remove(os.path.join(logfile_directory, tet_fname + '_log.txt'))
                                    os.rename(log_fpath,
                                              os.path.join(logfile_directory, tet_fname + '_log.txt'))
                                try:
                                    # moves the .ini files
                                    os.rename(ini_fpath, os.path.join(inifile_directory, tet_fname + '.ini'))
                                except FileExistsError:
                                    os.remove(os.path.join(inifile_directory, tet_fname + '.ini'))
                                    os.rename(ini_fpath, os.path.join(inifile_directory, tet_fname + '.ini'))

                                os.rename(tet_path, os.path.join(no_spike_dir, tet_fname))

                                x = 0

                            except PermissionError:
                                x = 1
                            processing = 0

            try:
                q.task_done()
            except ValueError:
                pass


def check_klusta_ready(self, directory, settings_fname=''):
    klusta_ready = True

    with open(settings_fname, 'r+') as filename:
        settings = json.load(filename)

    settings['NumThreads'] = str(self.Multithread.text())
    settings['Cores'] = str(self.core_num.text())

    with open(settings_fname, 'w') as filename:
        json.dump(settings, filename)

    if settings['NumFet'] > 4:
        self.choice = ''
        self.LogError.myGUI_signal.emit('ManyFet')

        while self.choice == '':
            time.sleep(1)

        if self.choice == QtGui.QMessageBox.No:
            klusta_ready = False
        elif self.choice == QtGui.QMessageBox.Yes:
            klusta_ready = True

    if directory == 'No Directory Currently Chosen!':
        self.choice = ''
        self.LogError.myGUI_signal.emit('NoDir')
        while self.choice == '':
            time.sleep(1)

        if self.choice == QtGui.QMessageBox.Ok:
            return False

    if 'Google Drive' in directory:
        self.choice = ''
        self.LogError.myGUI_signal.emit('GoogleDir')
        while self.choice == '':
            time.sleep(1)

        if self.choice == QtGui.QMessageBox.Yes:
            klusta_ready = True
        elif self.choice == QtGui.QMessageBox.No:
            klusta_ready = False

    return klusta_ready


def check_analyzeable(self, sub_directory_fullpath, set_file, tet_list):
    error = []
    analyzeable = True
    f_list = os.listdir(sub_directory_fullpath)  # finds the files within that directory

    if not tet_list:
        self.LogAppend.myGUI_signal.emit(
            '[%s %s]: The %s \'.set\' file has no tetrodes to analyze!' % (
                str(datetime.datetime.now().date()),
                str(datetime.datetime.now().time())[
                :8], set_file))

        # appends error to error list
        error.append('\tThe ' +
                     set_file + " '.set' file had no tetrodes to analyze, couldn't perform analysis.\n")
        analyzeable = False

        # if eeg not in the f_list move the files to the missing associated file folder
    if not set([set_file + '.eeg', set_file + '.pos']).issubset(f_list):

        self.LogAppend.myGUI_signal.emit(
            '[%s %s]: There is no %s or %s file in this folder, skipping analysis!' % (
                str(datetime.datetime.now().date()),
                str(datetime.datetime.now().time())[
                :8], set_file + '.eeg', set_file + '.pos'))

        # skipped = 1

        error.append('\tThe "' + str(
            set_file) +
                     '" \'.set\' file was not analyzed due to not having an \'.eeg\' and a \'.pos\' file.\n')
        analyzeable = False

    elif set_file + '.eeg' not in f_list:

        self.LogAppend.myGUI_signal.emit(
            '[%s %s]: There is no %s file in this folder, skipping analysis!' % (
                str(datetime.datetime.now().date()),
                str(datetime.datetime.now().time())[
                :8], set_file + '.eeg'))

        # skipped = 1
        error.append('\tThe "' + set_file +
                     '" \'.set\' file was not analyzed due to not having an \'.eeg\' file.\n')
        analyzeable = False

        # if .pos not in the f_list move the files to the missing associated file folder
    elif set_file + '.pos' not in f_list:

        associated_files = [file for file in f_list if set_file in file]
        missing_dir = os.path.join(sub_directory_fullpath, 'MissingAssociatedFiles')
        if not os.path.exists(missing_dir):
            os.makedirs(missing_dir)

        for file in associated_files:
            os.rename(os.path.join(sub_directory_fullpath, file), os.path.join(missing_dir, file))

        self.LogAppend.myGUI_signal.emit(
            '[%s %s]: There is no %s file in this folder, skipping analysis!' % (
                str(datetime.datetime.now().date()),
                str(datetime.datetime.now().time())[
                :8], set_file + '.pos'))
        # skipped = 1
        error.append('\tThe "' + set_file +
                     '" \'.set\' file was not analyzed due to not having a \'.pos\' file.\n')
        analyzeable = False

    if not analyzeable:
        associated_files = [file for file in f_list if set_file in file]
        missing_dir = os.path.join(sub_directory_fullpath, 'MissingAssociatedFiles')
        if not os.path.exists(missing_dir):
            os.makedirs(missing_dir)

        for file in associated_files:
            os.rename(os.path.join(sub_directory_fullpath, file), os.path.join(missing_dir, file))

    return analyzeable, error


def batchtint(main_window, directory, subdirectory):

    batch_settings_window = main_window.batch_tint_settings_window

    # if batch_settings_window is None:
    #    main_window.create_settings_signal.myGUI_signal.emit('create')

    settings_fname = main_window.batch_tint_settings_window.settings_fname

    # klusta_ready = check_klusta_ready(main_window, directory, main_window.parameters['tintsettings'])
    klusta_ready = True

    if klusta_ready:
        main_window.LogAppend.myGUI_signal.emit(
            '[%s %s]: Analyzing the following directory: %s!' % (str(datetime.datetime.now().date()),
                                                                 str(datetime.datetime.now().time())[
                                                                 :8], directory))
        # ------------- find all subdirectories within directory -------------------------------------

        sub_directories = [d for d in os.listdir(directory) if
                           os.path.isdir(os.path.join(directory, d)) and d not in ['Processed', 'Converted']]

        if not sub_directories:

            # message that shows how many files were found
            main_window.LogAppend.myGUI_signal.emit(
                '[%s %s]: There are no files to analyze in this directory!' % (str(datetime.datetime.now().date()),
                                                                               str(datetime.datetime.now().time())[
                                                                               :8]))
            return

        else:
            # message that shows how many files were found
            main_window.LogAppend.myGUI_signal.emit(
                '[%s %s]: Found %d files in the directory!' % (str(datetime.datetime.now().date()),
                                                               str(datetime.datetime.now().time())[
                                                               :8], len(sub_directories)))

        # ----------- cycle through each file and find the tetrode files ------------------------------------------

        for sub_directory in sub_directories:  # finding all the folders within the directory
            if subdirectory == sub_directory:

                try:
                    dir_new = os.path.join(directory, sub_directory)  # sets a new filepath for the directory
                    f_list = os.listdir(dir_new)  # finds the files within that directory
                    set_file = [file for file in f_list if '.set' in file]  # finds the set file

                    if not set_file:  # if there is no set file it will return as an empty list
                        # message saying no .set file
                        main_window.LogAppend.myGUI_signal.emit(
                            '[%s %s]: The following folder contains no \'.set\' file: %s' % (
                                str(datetime.datetime.now().date()),
                                str(datetime.datetime.now().time())[
                                :8], str(sub_directory)))
                        continue
                    # runs the function that will perform the klusta'ing
                    klusta(main_window, sub_directory, directory, settings_fname)

                except NotADirectoryError:
                    # if the file is not a directory it prints this message
                    main_window.LogAppend.myGUI_signal.emit(
                        '[%s %s]: %s is not a directory!' % (
                            str(datetime.datetime.now().date()),
                            str(datetime.datetime.now().time())[
                            :8], str(sub_directory)))
                    continue

                break