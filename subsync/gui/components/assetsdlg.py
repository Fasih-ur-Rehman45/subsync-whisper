import wx
from subsync.gui.downloadwin import DownloadWin
from subsync.gui.busydlg import BusyDlg, showBusyDlgAsyncJob
from subsync.gui.components import popups
from subsync.assets import assetManager
from subsync.data import descriptions
from subsync.settings import settings
from subsync.error import Error
from subsync.synchro import transcribe, translate, langdetect, route
from subsync.data import languages
from subsync import utils
import threading

import logging
logger = logging.getLogger(__name__)


def validateAssets(parent, tasks, updateAssets=True, askForLang=True, autoSave=False):
    if askForLang and settings().showLanguageNotSelectedPopup:
        if not askForLangSelection(parent, tasks):
            return False

    assets = assetManager().getAssetsForTasks(tasks)

    if assets.notInstalled():
        updateAssetList(parent)

    assets.validate()

    if assets.notInstalled():
        if not askForDownloadAssets(parent, assets.notInstalled()):
            return False

    if updateAssets and assets.hasUpdate():
        askForUpdateAssets(parent, assets.hasUpdate())

    if needsSpeechModel(tasks) and transcribe.isModelInstalled() is False:
        if not askForDownloadSpeechModel(parent):
            return False

    translated = translatedTasks(tasks)
    if translated and translate.isModelInstalled() is False:
        if not askForDownloadTranslationModel(parent, translated[0].sub.lang):
            return False

    return True

def needsSpeechModel(tasks):
    return any(route.getRoute(task.sub, task.ref) in route.WHISPER for task in tasks)

def translatedTasks(tasks):
    ''' Tasks whose subtitles are machine-translated to English for matching. '''
    return [ task for task in tasks if route.getRoute(task.sub, task.ref) == route.PIVOT ]

def askForDownloadTranslationModel(parent, lang):
    msg  = [ _('{} subtitles are matched with the speech by translating them to '
            'English on this computer, only for matching (your subtitles are not '
            'changed).').format(languages.getName(lang)) ]
    msg += [ _('The translation model must be downloaded once ({}) and is kept for later use.')
            .format(utils.fileSizeFmt(translate.modelSize)) ]
    msg += [ '', _('Download now?') ]
    title = _('Download translation model')
    flags = wx.YES_NO | wx.ICON_QUESTION
    with wx.MessageDialog(parent, '\n'.join(msg), title, flags) as dlg:
        if dlg.ShowModal() == wx.ID_YES:
            return downloadModel(parent, translate.downloadModel, translate.modelSize,
                    _('Download translation model'),
                    _("Couldn't download the translation model, check your internet connection"))
    return False

def detectLanguages(parent, tasks):
    ''' Detect audio language of references that don't have one set, before
    tasks are validated. When it isn't detected, the user has to select it as
    before. '''
    tasks = [ task for task in tasks if langdetect.needsDetection(task) ]
    if not tasks:
        return

    if transcribe.isModelInstalled() is False:
        msg = _('The audio language is not selected. SubSync can detect it with '
                'the Whisper speech recognition model.')
        if not askForDownloadSpeechModel(parent, msg):
            return

    for no, task in enumerate(tasks):
        msg = _('Detecting audio language...')
        if len(tasks) > 1:
            msg += ' ({}/{})'.format(no + 1, len(tasks))
        try:
            showBusyDlgAsyncJob(parent, msg, langdetect.detect, task)
        except Exception as err:
            logger.warning('audio language detection failed: %r', err, exc_info=True)

def askForDownloadSpeechModel(parent, reason=None):
    size = transcribe.getModelSize()
    msg  = [ reason or _('Speech in this language is recognized with the Whisper speech recognition model.') ]
    if size:
        msg += [ _('It must be downloaded once ({}) and is kept for later use.').format(utils.fileSizeFmt(size)) ]
    msg += [ '', _('Download now?') ]
    title = _('Download speech recognition model')
    flags = wx.YES_NO | wx.ICON_QUESTION
    with wx.MessageDialog(parent, '\n'.join(msg), title, flags) as dlg:
        if dlg.ShowModal() == wx.ID_YES:
            return downloadSpeechModel(parent)
    return False

def downloadSpeechModel(parent):
    return downloadModel(parent, transcribe.downloadModel, transcribe.getModelSize(),
            _('Download speech recognition model'),
            _("Couldn't download the speech recognition model, check your internet connection"))

def downloadModel(parent, download, size, title, failure):
    ''' Run `download` (transcribe.downloadModel or translate.downloadModel)
    with a progress window. '''
    state = { 'pos': 0, 'size': size, 'done': False, 'error': None, 'cancel': False }

    def onProgress(pos, size):
        state['pos'], state['size'] = pos, size

    def run():
        try:
            state['done'] = download(runCb=lambda: not state['cancel'], progressCb=onProgress)
        except Exception as err:
            state['error'] = err

    thread = threading.Thread(target=run, name='ModelDownload', daemon=True)
    thread.start()

    style = wx.PD_APP_MODAL | wx.PD_CAN_ABORT | wx.PD_ELAPSED_TIME | wx.PD_REMAINING_TIME
    dlg = wx.ProgressDialog(title, _('Downloading...') + ' ' * 40, maximum=1000,
            parent=parent, style=style)
    try:
        while thread.is_alive():
            pos, size = state['pos'], state['size']
            msg = _('Downloading...') + ' ' + utils.fileSizeFmt(pos)
            if size:
                msg += ' / ' + utils.fileSizeFmt(size)
                cont, _skip = dlg.Update(min(int(1000 * pos / size), 999), msg)
            else:
                cont = dlg.Pulse(msg)[0]
            if not cont:
                state['cancel'] = True
                break
            wx.MilliSleep(200)
    finally:
        dlg.Destroy()

    thread.join()
    if state['error'] is not None:
        raise Error(failure).add('details', str(state['error']))
    return state['done']

def updateAssetList(parent):
    listUpdater = assetManager().getAssetListUpdater()
    if not listUpdater.isRunning() and not listUpdater.isUpdated():
        listUpdater.run()

    if listUpdater.isRunning():
        with BusyDlg(parent, _('Downloading assets list...')) as dlg:
            dlg.ShowModalWhile(listUpdater.isRunning)

    return listUpdater.isUpdated()

def askForDownloadAssets(parent, assetList):
    msg  = [ _('Following assets must be download to continue:') ]
    msg += [ ' - ' + asset.getPrettyName() for asset in assetList ]
    msg += [ '', _('Download now?') ]
    title = _('Download assets')
    flags = wx.YES_NO | wx.ICON_QUESTION
    with wx.MessageDialog(parent, '\n'.join(msg), title, flags) as dlg:
        if dlg.ShowModal() == wx.ID_YES:
            return downloadAssets(parent, assetList)
    return False

def askForUpdateAssets(parent, assetList):
    msg  = [ _('Following assets could be updated:') ]
    msg += [ ' - ' + asset.getPrettyName() for asset in assetList ]
    msg += [ '', _('Update now?') ]
    title = _('Update assets')
    flags = wx.YES_NO | wx.ICON_QUESTION
    with wx.MessageDialog(parent, '\n'.join(msg), title, flags) as dlg:
        if dlg.ShowModal() == wx.ID_YES:
            return downloadAssets(parent, assetList)
    return False

def downloadAssets(parent, assetList):
    for asset in assetList:
        with DownloadWin(parent, asset) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return False
    return True

def askForLangSelection(parent, tasks):
    msg = [ _('No language selected for:') ]
    missingLang = False
    for task in tasks:
        if not task.sub.lang:
            msg.append(_('subtitles: ') + task.sub.path)
            missingLang = True
        if not task.ref.lang:
            msg.append(_('references: ') + task.ref.path)
            missingLang = True

    if missingLang:
        msg += [ '', descriptions.noLanguageSelectedQuestion ]
        title = _('No language selected')
        return popups.showConfirmationPopup(parent, '\n'.join(msg), title,
                confirmKey='showLanguageNotSelectedPopup')

    return True
