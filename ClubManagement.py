# uncompyle6 version 3.9.0
# Python bytecode version base 2.7 (62211)
# Decompiled from: Python 3.9.13 (tags/v3.9.13:6de2ca5, May 17 2022, 16:36:42) [MSC v.1929 64 bit (AMD64)]
# Embedded file name: ./BBLobby\BBManagement\ClubManagement.py
# Compiled at: 2018-04-30 08:10:04
import BB2DbObjects, BBExceptionDesc, BB2DbObjectsImpl, BB2Achievements, ServerNotifications
from BBEnums import SkillCategories, PlayerTypeSkills, ESkillListing, ECharacs
from BBEnums.Races import ERaces
from BBMessages.GameServiceData import EGameCompletionStatus
from BBMessages import BB2Data, BB2DbRowsMsg, LobbyData, RulesEngineData
from BBManagement import StaticData, EMatchType
from DataBase.DBManager import DBManager
from Exceptions.PyLobbyException import PyLobbyException
from Log import GetLog, ELogs
from DataCache import DataCache
from Managers import ShardingManager, MiscManager
from Managers.MatchMakingManager import EAutoMatchStatus
import ServerConfig, Utils
from datetime import datetime
import random, json, traceback
from whichdb import dbm
TeamNameMinLength = 3
TeamNameMaxLength = 48
CashOnTeamCreate = 1000000
BuyableItemPrices = {'popularity': 10000, 'cheerleaders': 10000, 'apothecary': 50000, 'assistantCoaches': 10000}
MaxCheerleaders = 10
MaxRerolls = 8
MaxAssistantCoaches = 10
MaxAssistantPopularity = 18
MaxApothecary = 1
StarPlayerRace = 26
SkillDividor = 1000
MaxPlayerPerTeam = 16
MaxPopularity = 18
SkillValue = 20000
DoubleSkillValue = 30000
MVorAVValue = 30000
AGValue = 40000
STValue = 50000
MaxCharacValue = 10
LightCasualties = [
 1, 2, 3, 4, 5, 6, 7, 8, 9]
LightMngCasualties = [2, 3, 4, 5, 6, 7, 8, 9]
CasualtyDead = 18
DiceIncreaseARorMV = 10
DiceIncreaseAG = 11
DiceIncreaseST = 12
DicSkillToCharacs = {ESkillListing.IncreaseStrength: ECharacs.ST, ESkillListing.IncreaseAgility: ECharacs.AG, 
   ESkillListing.IncreaseMovement: ECharacs.MV, 
   ESkillListing.IncreaseArmour: ECharacs.AV}
DefaultSpirallingExpenses = {'Ranges': [{'From': 0, 'To': 1750, 'Value': 0}, {'From': 1750, 'To': 1900, 'Value': 10000}, {'From': 1900, 'To': 2050, 'Value': 20000}, {'From': 2050, 'To': 2200, 'Value': 30000}, {'From': 2200, 'To': 2350, 'Value': 40000}, {'From': 2350, 'To': 2500, 'Value': 50000}, {'From': 2500, 'To': 2650, 'Value': 60000}], 'AboveMax': {'Step': 150, 'StepValue': 10000, 'TeamValue': 2650, 'ConstantValue': 60000}}

def GetTeamMaxGold():
    return ServerConfig.Config().GetCachedValue('BBTeamMaxGold', 2000000000)


def RollDice(rollType):
    diceTokens = rollType.split('D')
    nbDice = 1
    diceValue = 6
    if len(diceTokens) != 2:
        GetLog(ELogs.General).error('RollDice - Dice Parsing Error %s Returning D6 result', rollType)
    result = 0
    for i in range(nbDice):
        result += random.randint(1, diceValue)

    return result


class Race(BB2DbObjects.RulesRaces):

    @classmethod
    def GetPlayerTypesInfo(cls, IdRaces):
        query = ' SELECT * FROM bb_rules_player_types WHERE IdRaces != 26 AND IdRaces != 27 AND IdRaces != 30 AND IdRaces != 43'
        lstRows = DBManager().Query(query, IdRaces)
        dicResult = {}
        for row in lstRows:
            dicResult[row['ID']] = row

        GetLog(ELogs.General).info(dicResult)
        return dicResult

    @classmethod
    def GetByPlayerTypes(cls, PlayerTypes):
        return DBManager().QueryOneValue(('SELECT * FROM bb_rules_player_types WHERE IdRaces != 26 AND IdRaces != 27 AND IdRaces != 30 AND IdRaces != 43').format(PlayerTypes))


class TeamListing(BB2DbObjectsImpl.TeamListing):
    OmmitedFields = [
     '_dboCarreerStats', '_carreerStatsLoaded', '_ownedCardsLoaded', 
     '_rowsOwnedCards', '_stadiumStructures']

    def __init__(self):
        BB2DbObjectsImpl.TeamListing.__init__(self)
        self._dboCarreerStats = None
        self._carreerStatsLoaded = False
        self._rowsOwnedCards = None
        self._ownedCardsLoaded = False
        self._stadiumStructures = None
        return

    def HasGameInvitationPending(self):
        query = 'SELECT COUNT(*) FROM bb_game_invitation \n                   WHERE idTeamInviting=%s \n                   OR   idTeamInvited=%s'
        count = 0
        if DBManager().HasTable('bb_game_invitation'):
            count = DBManager().QueryOneValue(query, (self.ID, self.ID))
        if count > 0:
            return True
        else:
            return False

    def LoadCarreerStatsIfNeeded(self):
        if self._carreerStatsLoaded == False:
            self._dboCarreerStats = BB2DbObjects.StatisticsTeams.FindFirst(idTeamListing=self.ID, category='CARREER')
            self._carreerStatsLoaded = True

    def GetNbMatchPlayed(self):
        self.LoadCarreerStatsIfNeeded()
        if self._dboCarreerStats == None:
            return 0
        else:
            return self._dboCarreerStats.matchPlayed

    def ForceReloadOwnedCards(self):
        self._ownedCardsLoaded = False
        return self.GetOwnedCards()

    def GetOwnedCards(self):
        if self._ownedCardsLoaded == False:
            self._rowsOwnedCards = []
            query = ' SELECT bb_team_cards.* FROM bb_team_cards WHERE idTeamListing=%s'
            rowsTeamCard = DBManager().Query(query, self.ID)
            cardsById = DataCache().Get('CardsById')
            for row in rowsTeamCard:
                row['DataCard'] = cardsById.get(row['idCard'], None)
                self._rowsOwnedCards.append(row)

            self._ownedCardsLoaded = True
        return self._rowsOwnedCards

    def GetStadiumStructures(self):
        if self._stadiumStructures != None:
            return self._stadiumStructures
        else:
            query = 'SELECT bb_rules_cards.DataConstant FROM bb_team_cards,bb_rules_cards\n                   WHERE bb_team_cards.idCard= bb_rules_cards.ID \n                   AND idTeamListing=%s\n                   AND IdCardTypes=%s'
            rows = DBManager().Query(query, (self.ID, BB2Data.ECardType.Structure))
            self._stadiumStructures = [ x['DataConstant'] for x in rows ]
            return self._stadiumStructures

    def GetStadiumStructureIds(self):
        query = 'SELECT bb_rules_cards.ID FROM bb_team_cards,bb_rules_cards\n                   WHERE bb_team_cards.idCard= bb_rules_cards.ID \n                   AND idTeamListing=%s\n                   AND IdCardTypes=%s'
        rows = DBManager().Query(query, (self.ID, BB2Data.ECardType.Structure))
        return [ x['ID'] for x in rows ]

    def GetStadiumStructureId(self):
        ids = self.GetStadiumStructureIds()
        if len(ids) == 0:
            return 0
        return ids[0]

    def ComputeSpirallingExpenses(self, spirallingParams=DefaultSpirallingExpenses):
        for tvRange in spirallingParams['Ranges']:
            if self.value >= tvRange['From'] and self.value < tvRange['To']:
                return tvRange['Value']

        aboveMax = spirallingParams['AboveMax']
        if self.value < aboveMax['TeamValue']:
            GetLog(ELogs.Handlers).error('Error computing team spirraling expenses : TV : %d not matched %d' % self.value)
            return 0
        spiralling = aboveMax['ConstantValue'] + (self.value - aboveMax['TeamValue']) / aboveMax['Step'] * aboveMax['StepValue']
        return spiralling

    def AddCard(self, nbCards, rowCardData, **kwargs):
        import CardsManagement, CoachManagement
        dboCoachProgression = CoachManagement.EnsureAndGetCoachProgression(self.idCoach)
        handler = CardsManagement.GetTeamCardAcquisitionHandler(dboCoachProgression, self, rowCardData)
        for i in range(nbCards):
            handler.Give(**kwargs)

    def AddCheerleaderCard(self, nbCards):
        import CardsManagement
        if nbCards <= 0:
            return
        rowCardData = CardsManagement.GetCardDataByNameFromCache('Cheerleader')
        self.AddCard(nbCards, rowCardData)

    def AddFFCard(self, nbCards):
        import CardsManagement
        if nbCards <= 0:
            return
        nbMaxFF = ServerConfig.Config().GetCachedValue('BBFanFactorMaxQuantity', 18)
        rowCardData = CardsManagement.GetCardDataByNameFromCache('FanFactor')
        self.AddCard(nbCards, rowCardData, maxQuantity=nbMaxFF)

    def RemoveFFCard(self, nbCards):
        if nbCards <= 0:
            return
        dboCard = BB2DbObjects.RulesCards.CacheFindFirst(DataConstant='FanFactor')
        dboTeamCardsFF = BB2DbObjects.TeamCards.Find(idTeamListing=self.ID, idCard=dboCard.ID)
        for i in range(nbCards):
            if i >= len(dboTeamCardsFF):
                return
            dboTeamCardsFF[i].Delete()

    def AddRerollCard(self, nbCards):
        import CardsManagement
        if nbCards <= 0:
            return
        rowCardData = CardsManagement.GetCardDataByNameFromCache('Reroll')
        self.AddCard(nbCards, rowCardData)

    def AddApothecaryCard(self, nbCards):
        import CardsManagement
        if nbCards <= 0:
            return
        rowCardData = CardsManagement.GetCardDataByNameFromCache('Apothecary')
        self.AddCard(nbCards, rowCardData)

    def AddAssistantCard(self, nbCards):
        import CardsManagement
        if nbCards <= 0:
            return
        rowCardData = CardsManagement.GetCardDataByNameFromCache('Assistant')
        self.AddCard(nbCards, rowCardData)

    def AddNecromancerCard(self, nbCards):
        import CardsManagement
        if nbCards <= 0:
            return
        rowCardData = CardsManagement.GetCardDataByNameFromCache('Necromancer')
        self.AddCard(nbCards, rowCardData)

    def GetTeamCardsByTypeMsgs(self):
        ownedCards = self.GetOwnedCards()
        dboCardTypes = BB2DbObjects.RulesCardTypes.Find()
        msgTeamCardsByType = []
        for dboCardType in dboCardTypes:
            msg = BB2Data.TeamCardsByType()
            msg.idCardType = dboCardType.ID
            msg.maxCardOfThisType = dboCardType.MaxCards
            msgTeamCardsByType.append(msg)

        dicOwnedCards = Utils.Dictionnarize(ownedCards, (lambda x: x['DataCard']['IdCardTypes']))
        for msg in msgTeamCardsByType:
            rowTeamCardsOfType = dicOwnedCards.get(msg.idCardType, None)
            if rowTeamCardsOfType == None:
                continue
            for rowTeamCard in rowTeamCardsOfType:
                rowDataCard = rowTeamCard['DataCard']
                teamCardData = BB2Data.TeamCard()
                Utils.Assign(rowDataCard, teamCardData.rowCard)
                teamCardData.idTeam = self.ID
                teamCardData.idCard = rowDataCard['ID']
                teamCardData.idTeamCard = rowTeamCard['id']
                teamCardData.url = rowTeamCard['url']
                msg.teamCards.append(teamCardData)

        return msgTeamCardsByType

    def GetNbCardsFromDataConstant(self, dataConstant):
        query = 'SELECT COUNT(*) FROM bb_team_cards bbtc,bb_rules_cards bbrc \n                   WHERE bbtc.idTeamListing = %s\n                   AND bbtc.idCard = bbrc.ID\n                   AND  bbrc.DataConstant=%s'
        return DBManager().QueryOneValue(query, (self.ID, dataConstant))

    def GetNbCardsFromId(self, idCard):
        query = 'SELECT COUNT(*) FROM bb_team_cards bbtc \n                   WHERE bbtc.idTeamListing = %s AND bbtc.idCard = %s'
        return DBManager().QueryOneValue(query, (self.ID, idCard))

    def UpgradeStadium(self):
        if self.HasGameInvitationPending():
            raise PyLobbyException(BBExceptionDesc.TeamHasBeenInvited)
        stadiumLevelsTable = StaticData.StaticDataManager().GetStaticDataContentByName('StadiumLevelsTable.StadiumLevelsTable')
        nextStadiumLevel = None
        for stadiumLevel in stadiumLevelsTable.levels:
            if stadiumLevel.level > self.stadiumLevel:
                nextStadiumLevel = stadiumLevel
                break

        if nextStadiumLevel == None:
            raise PyLobbyException(BBExceptionDesc.StadiumNoMoreUpgradeAvailable)
        if self.CanAfford(nextStadiumLevel.goldPrice) == False:
            raise PyLobbyException(BBExceptionDesc.NotEnoughCash)
        self.stadiumLevel = nextStadiumLevel.level
        self.ChangeCash(-nextStadiumLevel.goldPrice)
        self.ComputeValue()
        self.Save()
        return

    @classmethod
    def GetRosters(cls, lstTeamIds, getAllStats=False, statsCategory=None, **kwargs):
        getPlayers = kwargs.get('getPlayers', True)
        lstRosters = []
        if len(lstTeamIds) == 0:
            return lstRosters
        else:
            lstTeams = TeamListing.Find(ID=lstTeamIds)
            lstTeamStats = []
            leagueSelect = BB2DbObjects.League.GetTablePrefixedColumnNamesString()
            competitionSelect = BB2DbObjects.Competition.GetTablePrefixedColumnNamesString()
            idCoaches = [ x.idCoach for x in lstTeams if x.idCoach != 0 ]
            dicCoachInfos = {}
            if len(idCoaches) > 0:
                query = 'SELECT id,name FROM account WHERE id IN (%s)' % Utils.GetStrSepList(idCoaches)
                rowsCoachs = DBManager().Query(query)
                for rowCoach in rowsCoachs:
                    dicCoachInfos[rowCoach['id']] = rowCoach['name']

            query = 'SELECT name FROM account WHERE id IN (%s)'
            strLstTeams = Utils.GetStrSepList(lstTeamIds)
            query = 'SELECT %s,%s,bb_competition_team.idTeam as `bb_competition_team.idTeam`  \n                FROM bb_competition_team \n                LEFT JOIN bb_competition ON bb_competition.id = bb_competition_team.idCompetition\n                LEFT JOIN bb_league ON bb_league.id = bb_competition.idLeague                 \n                WHERE bb_competition_team.idTeam IN (%s)\n                AND bb_competition_team.idTeamCompetitionStatus = %s' % (leagueSelect, competitionSelect, strLstTeams, BB2Data.ECompetitionRegistrationStatus.Registered)
            rowsTeamCompetitions = DBManager().Query(query)
            rowsTeamCompetitions = Utils.ExplodePrefixedRows(rowsTeamCompetitions)
            query = ' SELECT bb_league.*,bb_league_team_registration.idTeam\n                    FROM bb_league_team_registration\n                    LEFT JOIN bb_league ON bb_league.id = bb_league_team_registration.idLeague\n                    WHERE bb_league_team_registration.idTeam IN (%s)\n                    AND bb_league_team_registration.registrationStatus = %d\n                ' % (Utils.GetStrSepList(lstTeamIds), BB2Data.ELeagueRegistrationStatus.Registered)
            rowsTeamsLeagues = DBManager().Query(query)
            dicTeamLeagues = {}
            for row in rowsTeamsLeagues:
                dicTeamLeagues[row['idTeam']] = row

            if getAllStats == True:
                lstTeamStats = BB2DbObjects.StatisticsTeams.Find(idTeamListing=lstTeamIds)
            elif statsCategory != None and len(statsCategory) > 0:
                lstTeamStats = BB2DbObjects.StatisticsTeams.Find(idTeamListing=lstTeamIds, category=statsCategory)
            lstRankings = cls.GetRankings(lstTeamIds)
            if getPlayers:
                lstPlayers = PlayerListing.Find(idTeamListing=lstTeamIds)
                lstPlayersIds = [ x.ID for x in lstPlayers ]
                lstPlayerStats = []
                if getAllStats == True:
                    lstPlayerStats = BB2DbObjects.StatisticsPlayers.Find(idPlayerListing=lstPlayersIds)
                elif statsCategory != None and len(statsCategory) > 0:
                    lstPlayerStats = BB2DbObjects.StatisticsPlayers.Find(idPlayerListing=lstPlayersIds, category=statsCategory)
                lstSkills = BB2DbObjects.PlayerSkills.Find(idPlayerListing=lstPlayersIds)
                lstCasualties = BB2DbObjects.PlayerCasualties.Find(idPlayerListing=lstPlayersIds)
            emptyRegistration = {'idLeague': 0, 'registrationStatus': 0}
            for team in lstTeams:
                dicRoster = {}
                dicRoster['team'] = team
                dicRoster['registration'] = emptyRegistration
                dicRoster['players'] = []
                dicRoster['stats'] = filter((lambda x: x.idTeamListing == team.ID), lstTeamStats)
                dicRoster['rankings'] = filter((lambda x: x['idTeam'] == team.ID), lstRankings)
                dicRoster['mainRanking'] = None
                dicRoster['competitions'] = filter((lambda x: x['bb_competition_team']['idTeam'] == team.ID), rowsTeamCompetitions)
                dicRoster['rowLeague'] = dicTeamLeagues.get(team.ID, None)
                dicRoster['coachName'] = dicCoachInfos.get(team.idCoach, '')
                if getPlayers:
                    teamPlayers = filter((lambda x: x.idTeamListing == team.ID), lstPlayers)
                    for player in teamPlayers:
                        dicPlayer = {}
                        dicPlayer['player'] = player
                        dicPlayer['skills'] = filter((lambda x: x.idPlayerListing == player.ID), lstSkills)
                        dicPlayer['casualties'] = filter((lambda x: x.idPlayerListing == player.ID), lstCasualties)
                        dicPlayer['stats'] = filter((lambda x: x.idPlayerListing == player.ID), lstPlayerStats)
                        dicRoster['players'].append(dicPlayer)

                lstRosters.append(dicRoster)

            return lstRosters

    @classmethod
    def GetRankings(cls, teamIds):
        return []

    def DeleteRoster(self):
        import LeagueManagement
        LeagueManagement.CancelBidsImplyingTeam(self.ID, BB2Data.EBidStatus.Canceled, True)
        DeleteRosters([self.ID])

    def CanAfford(self, price):
        if self.cash >= price:
            return True
        if not self.flags & BB2Data.ETeamFlags.Experienced and self.flags & BB2Data.ETeamFlags.Custom:
            return True
        return False

    def GetPlayerList(self):
        return BB2DbObjects.PlayerListing.Find(idTeamListing=self.ID)

    def GetPendingMatchCalendar(self):
        raise Exception('NotImplemented')

    def CancelBidsIfNoMoreRoom(self):
        availableRosterNums = GetAvailableRosterNums(self.ID)
        if len(availableRosterNums) == 0:
            import LeagueManagement
            LeagueManagement.CancelActiveBidsFromTeam(self.ID, BB2Data.EBidStatus.Canceled, True)

    def TryBuyOrSellItem(self, **kwargs):
        """ Buy items specified in kwargs if possible, inconsistent 
            or invalid request will be silently skipped """
        if self.HasGameInvitationPending():
            raise PyLobbyException(BBExceptionDesc.TeamHasBeenInvited)
        if self.edited == 1:
            GetLog(ELogs.General).error('TryBuyOrSellItem - Team Id %d - is locked cannot process' % self.ID)
            return

        def processItem(objFieldName, nbItems, itemPrice, maxQuantity, alreadyPlayed):
            if nbItems == 0:
                return False
            currentQuantity = getattr(self, objFieldName)
            quantityAllowed = Utils.ZeroAtLeast(maxQuantity - currentQuantity)
            quantityToBuyOrSell = Utils.Clamp(nbItems, -currentQuantity, quantityAllowed)
            totalPrice = itemPrice * abs(quantityToBuyOrSell)
            if quantityToBuyOrSell > 0:
                if self.CanAfford(totalPrice):
                    currentQuantity += quantityToBuyOrSell
                    setattr(self, objFieldName, currentQuantity)
                    self.ChangeCash(-totalPrice)
                    return True
            else:
                currentQuantity += quantityToBuyOrSell
                setattr(self, objFieldName, currentQuantity)
                if not alreadyPlayed:
                    self.ChangeCash(totalPrice)
                return True
            return False

        alreadyPlayed = False
        if self.GetNbMatchPlayed() > 0:
            alreadyPlayed = True
        rerollPriceMultiplier = 1
        if alreadyPlayed:
            rerollPriceMultiplier = 2
        rerollPrice = BB2DbObjectsImpl.RulesRaces.GetRerollPrice(self.IdRaces)
        bChanged = False
        bChanged |= processItem('cheerleaders', kwargs.get('cheerleaders', 0), BuyableItemPrices['cheerleaders'], MaxCheerleaders, alreadyPlayed)
        bChanged |= processItem('apothecary', kwargs.get('apothecary', 0), BuyableItemPrices['apothecary'], MaxApothecary, alreadyPlayed)
        bChanged |= processItem('assistantCoaches', kwargs.get('assistantCoaches', 0), BuyableItemPrices['assistantCoaches'], MaxAssistantCoaches, alreadyPlayed)
        bChanged |= processItem('popularity', kwargs.get('popularity', 0), BuyableItemPrices['popularity'], MaxAssistantPopularity, alreadyPlayed)
        bChanged |= processItem('rerolls', kwargs.get('rerolls', 0), rerollPrice * rerollPriceMultiplier, MaxRerolls, alreadyPlayed)
        if bChanged:
            self.ComputeValue()
            self.Save()

    def TryBuyJourneyman(self, playerResult, newHead=-1):
        if self.HasGameInvitationPending():
            raise PyLobbyException(BBExceptionDesc.TeamHasBeenInvited)
        playerData = playerResult.playerData
        experienceEarned = playerResult.xp
        msgPlayer = BB2Data.Player()
        rowPlayer = msgPlayer.row
        rowPlayer.name = playerData.name
        rowPlayer.number = 0
        rowPlayer.idPlayerLevels = playerData.level
        rowPlayer.idPlayerTypes = playerData.idPlayerTypes
        rowPlayer.idHead = newHead if newHead > -1 else playerData.idHead
        isFree = playerData.contract == RulesEngineData.EContract.Zombie or playerData.contract == RulesEngineData.EContract.Rotter
        results = self.TryBuyPlayers([rowPlayer], isFree)

        def HandleCasualty(dboPlayer, idCasualty):
            if idCasualty != 0 and idCasualty != CasualtyCommotion:
                dboPlayer.AddCasualty(idCasualty)
                if idCasualty in LstMatchSuspendedCasualties:
                    dboPlayer.Suspend()
                    return True
            return False

        if len(results) > 0:
            dboPlayer = results[0]
            needSave = False
            if experienceEarned > 0:
                dboPlayer.EarnExperience(experienceEarned)
                needSave = True
            needSave = needSave or HandleCasualty(dboPlayer, playerResult.casualty1)
            needSave = needSave or HandleCasualty(dboPlayer, playerResult.casualty2)
            if needSave:
                dboPlayer.Save()
            playerResult.playerData.contract = RulesEngineData.EContract.RosterMember
            return dboPlayer
        else:
            return

    def IsCustomPhase(self):
        if not self.flags & BB2Data.ETeamFlags.Experienced and self.flags & BB2Data.ETeamFlags.Custom:
            return True
        return False

    def ChangeCash(self, Value):
        TempValue = self.cash + Value
        self.cash = Utils.ZeroAtLeast(TempValue)

    def TryBuyPlayers(self, lstPlayersToBuy, free=False):
        """ Buy players specified in param - inconsitent or invalid requests will be silently skipped """
        if self.HasGameInvitationPending():
            raise PyLobbyException(BBExceptionDesc.TeamHasBeenInvited)
        boughtPlayerDbos = []
        if len(lstPlayersToBuy) == 0:
            return boughtPlayerDbos
        else:
            currentRoster = self.GetPlayerList()
            bChanged = False
            lstRosterNumbers = [ x.number for x in currentRoster ]
            lstPlayerTypesMaximumReached = []
            for player in lstPlayersToBuy:
                player.IdRaces = Race.GetByPlayerTypes(player.idPlayerTypes)
                player.ID = 0
                if len(currentRoster) >= MaxPlayerPerTeam:
                    GetLog(ELogs.General).error('TryBuyPlayers - Team Id %d Max number of player reached' % self.ID)
                    continue
                if player.number == 0:
                    for i in range(1, MaxPlayerPerTeam + 1):
                        if i not in lstRosterNumbers:
                            player.number = i
                            break

                if player.number in lstRosterNumbers:
                    GetLog(ELogs.General).error('TryBuyPlayers - Team Id %d - Roster num %d Already used' % (self.ID, player.number))
                    continue
                nbPlayersOfThisType = len(filter((lambda x: x.idPlayerTypes == player.idPlayerTypes), currentRoster))
                dicPlayerTypesInfo = Race.GetPlayerTypesInfo(player.IdRaces)
                rowPlayerTypeInfo = dicPlayerTypesInfo.get(player.idPlayerTypes, None)
                if rowPlayerTypeInfo == None:
                    GetLog(ELogs.General).error('TryBuyPlayers - Team Id %d - Player Type %d not found for race:%d' % (self.ID, player.idPlayerTypes, player.IdRaces))
                    continue
                nbPlayersOfThisTypeAllowed = rowPlayerTypeInfo['MaxQuantity']
                if nbPlayersOfThisType >= nbPlayersOfThisTypeAllowed:
                    GetLog(ELogs.General).error('TryBuyPlayers - Team Id %d - Player Type %d Already Got %d' % (self.ID, player.idPlayerTypes, nbPlayersOfThisType))
                    continue
                if self.edited == 1:
                    GetLog(ELogs.General).error('TryBuyPlayers - Team Id %d - is locked cannot process' % self.ID)
                    continue
                price = 0 if free else rowPlayerTypeInfo['Price']
                if self.CanAfford(price):
                    self.ChangeCash(-price)
                    player.idPlayerLevels = 1
                    player.experience = 0
                    player.nbLevelsUp = 0
                    player.idTeamListing = self.ID
                    player.characsMovementAllowance = rowPlayerTypeInfo['CharacsMovementAllowance']
                    player.characsStrength = rowPlayerTypeInfo['CharacsStrength']
                    player.characsAgility = rowPlayerTypeInfo['CharacsAgility']
                    player.characsArmourValue = rowPlayerTypeInfo['CharacsArmourValue']
                    player.value = rowPlayerTypeInfo['Price'] / SkillDividor
                    player.IdRaces = self.IdRaces
                    dbPlayer = PlayerListing()
                    Utils.Assign(player, dbPlayer)
                    dbPlayer.Save()
                    bChanged = True
                    currentRoster.append(dbPlayer)
                    boughtPlayerDbos.append(dbPlayer)
                    lstRosterNumbers.append(dbPlayer.number)
                    if nbPlayersOfThisType >= nbPlayersOfThisTypeAllowed - 1:
                        lstPlayerTypesMaximumReached.append(player.idPlayerTypes)
                else:
                    GetLog(ELogs.General).error('TryBuyPlayers - Team Id %d - Buying Player Type %d not enough cash' % (self.ID, player.idPlayerTypes))
                    continue

            if bChanged:
                self.ComputeValue()
                if not self.IsValidated():
                    if len(currentRoster) >= ServerConfig.Config().GetCachedValue('BBTeamRosterValidationThreshold', 11):
                        self.validated = 1
                self.Save()
                self.CancelBidsIfNoMoreRoom()
                import LeagueManagement
                for idPlayerType in lstPlayerTypesMaximumReached:
                    LeagueManagement.CancelActiveBidsOnPlayerType(self.ID, idPlayerType, BB2Data.EBidStatus.Canceled, True)

            return boughtPlayerDbos

    def ProcessMiscChanges(self, miscChanges):
        if self.edited == 1:
            GetLog(ELogs.General).error('ProcessMiscChanges - Team Id %d - is locked cannot process' % self.ID)
            return
        if len(miscChanges) == 0:
            return
        bTeamChanged = False
        if miscChanges.has_key('TeamLeitmotiv'):
            self.leitmotiv = miscChanges['TeamLeitmotiv']
            bTeamChanged = True
        if miscChanges.has_key('TeamHistory'):
            self.background = miscChanges['TeamHistory']
            bTeamChanged = True
        if miscChanges.has_key('Color'):
            self.teamColor = int(miscChanges['Color'])
            bTeamChanged = True
        if miscChanges.has_key('Logo'):
            self.logo = int(miscChanges['logo'])
            bTeamChanged = True
        if bTeamChanged:
            self.Save()

    def TryFirePlayers(self, firedPLayers, forceRefund=False):
        """ Fire players specified in param - inconsitent or invalid requests will be silently skipped """
        if self.HasGameInvitationPending():
            raise PyLobbyException(BBExceptionDesc.TeamHasBeenInvited)
        idPlayersFired = []
        if self.edited == 1:
            GetLog(ELogs.General).error('TryFirePlayers - Team Id %d - is locked cannot process' % self.ID)
            return
        else:
            lstPlayers = PlayerListing.Find(ID=firedPLayers)
            bChanged = False
            campaignRefund = forceRefund and self.campaign == 1
            bIsTeamCustom = self.flags & BB2Data.ETeamFlags.Custom != 0
            query = "SELECT matchPlayed FROM bb_statistics_teams WHERE idTeamListing=%s AND category='CARREER' "
            nbMatchPlayed = DBManager().QueryOneValue(query, self.ID, 0)
            bCanRefund = nbMatchPlayed == 0 and not bIsTeamCustom or campaignRefund
            for player in lstPlayers:
                dicPlayerTypesInfo = Race.GetPlayerTypesInfo(self.IdRaces)
                if player.idTeamListing != self.ID:
                    GetLog(ELogs.General).error('TryFirePlayers - Team Id %d - Trying to fire player %d which is not part of that team - registered on Team  %d' % (self.ID, player.ID, player.idTeamListing))
                    continue
                rowPlayerType = dicPlayerTypesInfo.get(player.idPlayerTypes)
                if rowPlayerType == None:
                    GetLog(ELogs.General).error('TryFirePlayers - Team Id %d - Trying to fire player %d which type was not found on related race' % (self.ID, player.ID))
                else:
                    if bCanRefund:
                        GetLog(ELogs.General).error('TryFirePlayers - Team Id %d - Player %d REFUNDED' % (self.ID, player.ID))
                        self.ChangeCash(rowPlayerType['Price'])
                    else:
                        GetLog(ELogs.General).error('TryFirePlayers - Team Id %d - Player %d NO REFUND' % (self.ID, player.ID))
                    if nbMatchPlayed == 0:
                        if self.idCoach != 0:
                            if self.campaign == 1 and len(lstPlayers) > 1:
                                pass
                            else:
                                BB2Achievements.RunAchievementHandlers(self.idCoach, 'BB2Achievements.HandlerSimpleTrigger', ('SellPlayerThatDidNotPlay', ), None)
                try:
                    GetLog(ELogs.General).info('TryFirePlayers - Team Id %d - Firing player %d Number : %d Name %s- OK' % (self.ID, player.ID, player.number, player.name.encode('utf-8')))
                except:
                    GetLog(ELogs.General).info('TryFirePlayers - Team Id %d - Firing player %d Number : %d - OK' % (self.ID, player.ID, player.number))

                idPlayersFired.append(player.ID)
                import LeagueManagement
                with DBManager().EnsureTransaction():
                    LeagueManagement.CancelActiveBidsOnPlayer(player.ID, BB2Data.EBidStatus.Canceled)
                    query = 'DELETE FROM bb_league_marketplace_bids WHERE idPlayer=%s'
                    DBManager().Query(query, self.ID)
                    player.Delete()
                bChanged = True

            if bChanged:
                self.ComputeValue()
                self.Save()
            return idPlayersFired

    def _ComputeValue(self):
        playerValue = DBManager().QueryOneValue('SELECT SUM(value) FROM bb_player_listing\n                                                   WHERE idTeamListing=%s\n                                                   AND dead=0 AND matchSuspended=0', self.ID)
        rerollPrice = BB2DbObjectsImpl.RulesRaces.GetRerollPrice(self.IdRaces)
        owningsValue = self.popularity * BuyableItemPrices['popularity'] + self.apothecary * BuyableItemPrices['apothecary'] + self.cheerleaders * BuyableItemPrices['cheerleaders'] + self.assistantCoaches * BuyableItemPrices['assistantCoaches'] + rerollPrice * self.rerolls + max(self.cash - 150000, 0)
        teamValue = int(playerValue + owningsValue / 1000)
        self.value = teamValue
        return teamValue

    def ComputeValue(self, recomputeAllPayers=False):
        if recomputeAllPayers:
            dboPlayers = PlayerListing.Find(idTeamListing=self.ID)
            for dboPlayer in dboPlayers:
                dboPlayer.ComputeValue()
                dboPlayer.Save()

        playerValue = DBManager().QueryOneValue('SELECT SUM(value) FROM bb_player_listing\n                                                   WHERE idTeamListing=%s\n                                                   AND dead=0 AND matchSuspended=0', self.ID)
        ownedCards = self.GetOwnedCards()
        owningsValue = 0
        import CardsManagement, CoachManagement
        dboCoachProgression = CoachManagement.EnsureAndGetCoachProgression(self.idCoach)
        self.apothecary = 0
        self.assistantCoaches = 0
        self.cheerleaders = 0
        self.rerolls = 0
        self.popularity = 0
        for ownedCard in ownedCards:
            cardHandler = CardsManagement.GetTeamCardAcquisitionHandler(dboCoachProgression, self, ownedCard['DataCard'])
            owningsValue += cardHandler.GetTvModifier()
            self.apothecary = min(self.apothecary + cardHandler.GetEffectValueInt('Lrb6Apothecary'), MaxApothecary)
            self.assistantCoaches = min(self.assistantCoaches + cardHandler.GetEffectValueInt('Lrb6Assistant'), MaxAssistantCoaches)
            self.cheerleaders = min(self.cheerleaders + cardHandler.GetEffectValueInt('Lrb6Cheerleaders'), MaxCheerleaders)
            self.rerolls = min(self.rerolls + cardHandler.GetEffectValueInt('Lrb6TeamRerolls'), MaxRerolls)
            self.popularity = min(self.popularity + cardHandler.GetEffectValueInt('Lrb6FanFactor'), MaxPopularity)

        owningsValue += max((self.cash - 150000) / 1000, 0)
        self.value = int(playerValue + owningsValue)
        if self.idCoach != 0:
            BB2Achievements.RunAchievementHandlers(self.idCoach, 'BB2Achievements.HandlerTeamCharacs', (self, ['minValue']), None)
            matchPlayed = DBManager().QueryOneValue('SELECT SUM(matchPlayed) FROM bb_statistics_teams WHERE idTeamListing = %s', (self.ID,), 0)
            if matchPlayed == 0 and self.flags & BB2Data.ETeamFlags.Custom and self.value >= 2000:
                BB2Achievements.RunAchievementHandlers(self.idCoach, 'BB2Achievements.HandlerSimpleTrigger', ('CustomTeamValue2000', ), None)
        return self.value

    def ComputeLrb6Items(self):
        self.apothecary = 0
        self.assistantCoaches = 0
        self.cheerleaders = 0
        self.rerolls = 0
        self.popularity = 0
        import CardsManagement
        ownedCards = self.GetOwnedCards()
        for ownedCard in ownedCards:
            import CoachManagement
            dboCoachProgression = CoachManagement.EnsureAndGetCoachProgression(self.idCoach)
            cardHandler = CardsManagement.GetTeamCardAcquisitionHandler(dboCoachProgression, self, ownedCard['DataCard'])
            self.apothecary = min(self.apothecary + cardHandler.GetEffectValueInt('Lrb6Apothecary'), MaxApothecary)
            self.assistantCoaches = min(self.assistantCoaches + cardHandler.GetEffectValueInt('Lrb6Assistant'), MaxAssistantCoaches)
            self.cheerleaders = min(self.cheerleaders + cardHandler.GetEffectValueInt('Lrb6Cheerleaders'), MaxCheerleaders)
            self.rerolls = min(self.rerolls + cardHandler.GetEffectValueInt('Lrb6TeamRerolls'), MaxRerolls)
            self.popularity = min(self.popularity + cardHandler.GetEffectValueInt('Lrb6FanFactor'), MaxPopularity)

    def ProcessSpGainsCardEffet(self, effectName):
        import CardsManagement
        raise Exception('Deprecated')

    def GetSpGainsCardEffet(self, effectName):
        import CardsManagement
        ownedCards = self.GetOwnedCards()
        cyanEarned = 0
        import CoachManagement
        dboCoachProgression = CoachManagement.EnsureAndGetCoachProgression(self.idCoach)
        for ownedCard in ownedCards:
            dataCard = ownedCard['DataCard']
            cardHandler = CardsManagement.GetTeamCardAcquisitionHandler(dboCoachProgression, self, dataCard)
            if cardHandler.HasEffect(effectName):
                cyanEarned += cardHandler.GetEffectValueInt(effectName)
                GetLog(ELogs.General).info('Coach : %d - Earning %d SP on PostMatch with Effect : %s of card : %s', self.idCoach, cyanEarned, effectName, dataCard['DataConstant'])

        return cyanEarned

    def UpdatePlayerCount(self):
        self.nbPlayers = PlayerListing.Count(idTeamListing=self.ID)
        DBManager().Query('UPDATE bb_team_listing SET nbPlayers=%s WHERE ID=%s', (self.nbPlayers, self.ID))

    def UpdateLevelUpPending(self, bUpdateDb=True):
        query = 'SELECT COUNT(*) FROM bb_player_listing WHERE idTeamListing=%s AND nbLevelsUp>0'
        nbPlayerWithLevelup = DBManager().QueryOneValue(query, self.ID)
        currentLevelPendingStatus = 0
        if nbPlayerWithLevelup > 0:
            currentLevelPendingStatus = 1
        if currentLevelPendingStatus != self.levelupPending:
            if bUpdateDb == True:
                DBManager().Query('UPDATE bb_team_listing SET levelupPending=%s WHERE ID=%s', (currentLevelPendingStatus, self.ID))
            self.levelupPending = currentLevelPendingStatus

    def UpdateValidationStatus(self):
        queryUpdate = 'UPDATE bb_team_listing SET validated=%s WHERE ID=%s'
        if self.validated == 1 and self.nbPlayers >= 11:
            return
        if self.validated == 0 and self.nbPlayers >= 11:
            DBManager().Query(queryUpdate, (1, self.ID))
            self.validated = 1
        elif self.validated == 1 and self.nbPlayers < 11:
            query = "SELECT matchPlayed FROM bb_statistics_teams WHERE idTeamListing=%s AND category='CARREER' "
            nbMatchPlayed = DBManager().QueryOneValue(query, self.ID, 0)
            if nbMatchPlayed == 0:
                self.validated = 0
                DBManager().Query(queryUpdate, (0, self.ID))

    def HasLevelUpPending(self):
        """ Tells wether level up should be passed on some players of the team"""
        return self.levelupPending > 0

    def IsValidated(self):
        """ Tells wether team roster reached a minimal of purchased player"""
        return self.validated > 0

    def ComputeSpGains(self, matchRecord):
        return 0

    def ComputeXpGains(self, matchRecord):
        xpEarned = 0
        if self.ID == matchRecord.GetIdTeamConcession():
            return 0
        if self.ID == matchRecord.GetIdTeamWinner():
            xpEarned = ServerConfig.Config().GetCachedValue('BBCoachXpByWin', 13)
        elif matchRecord.IsDraw():
            xpEarned = ServerConfig.Config().GetCachedValue('BBCoachXpByDraw', 11)
        else:
            xpEarned = ServerConfig.Config().GetCachedValue('BBCoachXpByLoss', 10)
        return xpEarned

    def GetActiveLeague(self, leagueClass=BB2DbObjects.League):
        query = 'SELECT bb_league.* FROM bb_league_team_registration,bb_league WHERE bb_league.id = bb_league_team_registration.idLeague AND idTeam=%s AND registrationStatus=%s'
        rows = DBManager().Query(query, (self.ID, BB2Data.ELeagueRegistrationStatus.Registered))
        if len(rows) > 0:
            dboLeague = leagueClass()
            Utils.Assign(rows[0], dboLeague)
            return dboLeague
        else:
            return

    def HasStarPlayer(self):
        query = 'SELECT COUNT(*) FROM bb_player_listing WHERE idTeamListing=%s AND IdRaces=%s'
        nb = DBManager().QueryOneValue(query, (self.ID, StarPlayerRace))
        return nb > 0

    def EnsureStarPlayers(self, starPlayers):
        query = ' SELECT bb_player_listing.*,DataConstant FROM bb_player_listing,bb_rules_player_types \n                    WHERE bb_rules_player_types.IdRaces=%s \n                    AND bb_rules_player_types.ID = bb_player_listing.IdPlayerTypes\n                    AND bb_player_listing.idTeamListing=%s'
        rowsStarPlayers = DBManager().Query(query, (StarPlayerRace, self.ID))
        foundStarPlayers = []
        idsToDelete = []
        for row in rowsStarPlayers:
            if row['DataConstant'] not in starPlayers:
                idsToDelete.append(row['ID'])
            else:
                foundStarPlayers.append(row['DataConstant'])

        starPlayersToAdd = [ x for x in starPlayers if x not in foundStarPlayers ]
        changed = False
        for starPlayer in starPlayersToAdd:
            self.AddStarPlayerFromDataConstant(starPlayer)
            changed = True

        if len(idsToDelete) > 0:
            query = 'DELETE FROM bb_player_listing WHERE ID IN (%s)' % Utils.GetStrSepList(idsToDelete)
            DBManager().Query(query)
            changed = True
        if changed:
            self.ComputeValue()
            self.Save()

    def GetStarPlayers(self):
        return BB2DbObjects.PlayerListing.Find(idTeamListing=self.ID, IdRaces=StarPlayerRace)

    def AddStarPlayerFromDataConstant(self, dataConstant):
        availableRosterNums = GetAvailableRosterNums(self.ID)
        if len(availableRosterNums) == 0:
            raise PyLobbyException(BBExceptionDesc.InvalidData)
        dboStarPlayer = BB2DbObjects.RulesPlayerTypes.CacheFindFirst(DataConstant=dataConstant)
        if dboStarPlayer == None:
            raise PyLobbyException(BBExceptionDesc.PlayerNotFound)
        player = BB2DbObjects.PlayerListing()
        player.name = dboStarPlayer.LocaName
        player.idPlayerLevels = 1
        player.idPlayerTypes = dboStarPlayer.ID
        player.experience = 0
        player.nbLevelsUp = 0
        player.idTeamListing = self.ID
        player.number = availableRosterNums[0]
        player.characsMovementAllowance = dboStarPlayer.CharacsMovementAllowance
        player.characsStrength = dboStarPlayer.CharacsStrength
        player.characsAgility = dboStarPlayer.CharacsAgility
        player.characsArmourValue = dboStarPlayer.CharacsArmourValue
        player.value = dboStarPlayer.Price / SkillDividor
        player.age = 10
        player.IdRaces = dboStarPlayer.IdRaces
        player.star = 1
        player.Save()
        return

    def RemoveStarPlayers(self):
        query = 'DELETE FROM bb_player_listing WHERE idTeamListing=%s AND IdRaces=%s'
        DBManager().Query(query, (self.ID, StarPlayerRace))


class Skill(BB2DbObjects.RulesSkillListing):

    @classmethod
    def IsCharac(cls, idSkill):
        return idSkill in [ESkillListing.IncreaseAgility, ESkillListing.IncreaseArmour, ESkillListing.IncreaseMovement, ESkillListing.IncreaseStrength]


class StatisticsTeamAndCoachMixin(BB2DbObjects.StatisticsTeams):
    AverageStatsMapping = {'averageMatchRating': 'rating', 
       'averageSpectators': 'spectators', 
       'averageCashEarned': 'cashEarned', 
       'possessionBall': 'possessionBall', 
       'occupationOwn': 'occupationOwn', 
       'occupationTheir': 'occupationTheir'}
    StatsOmmitedFields = [
     'idTeamListing', 'averageMatchRating', 'averageSpectators', 'averageCashEarned', 
     'possessionBall', 'occupationOwn', 'occupationTheir']
    AverageFields = [
     'averageMatchRating', 'averageSpectators', 'averageCashEarned', 
     'possessionBall', 'occupationOwn', 'occupationTheir']
    OmmitedCopyFields = [
     'ID', 'category', 'idLeague', 'idLadder', 'idCompetition', 'active']

    def AddMatchStats(self, stats, **kwstats):
        matchCount = self.matchPlayed
        attrListToSum = [ field for field in self.__dict__.keys() if field not in self.StatsOmmitedFields ]
        for attr in attrListToSum:
            if hasattr(stats, attr):
                setattr(self, attr, getattr(self, attr) + getattr(stats, attr))

        for attr in self.AverageFields:
            try:
                mappedField = self.AverageStatsMapping[attr]
                statValue = 0
                if hasattr(stats, mappedField):
                    statValue = getattr(stats, mappedField)
                else:
                    try:
                        statValue = kwstats[mappedField]
                    except:
                        pass

                average = (getattr(self, attr) * matchCount + statValue) / (matchCount + 1)
                setattr(self, attr, average)
            except:
                pass

    def TakeStats(self, otherStats):
        attrListToCopy = [ field for field in self.__dict__.keys() if field not in self.OmmitedCopyFields ]
        for attr in attrListToCopy:
            if hasattr(otherStats, attr):
                setattr(self, attr, getattr(otherStats, attr))


class StatisticsTeam(BB2DbObjects.StatisticsTeams, StatisticsTeamAndCoachMixin):
    OmmitedFields = [
     'inflictedPushOuts']

    def __init__(self):
        BB2DbObjects.StatisticsTeams.__init__(self)
        self.inflictedPushOuts = 0


class StatisticsCoach(BB2DbObjects.StatisticsCoach, StatisticsTeamAndCoachMixin):
    pass


class PlayerListing(BB2DbObjects.PlayerListing):
    DicLevels = {1: 5, 2: 15, 3: 30, 4: 50, 5: 75, 6: 175, 7: 1000}
    OmmitedFields = [
     '_dboSkills', '_skillIds', '_dboCasualties', '_dicSkillsDbo']

    def __init__(self):
        BB2DbObjects.PlayerListing.__init__(self)
        self._dboSkills = None
        self._dicSkillsDbo = Utils.Dictionnarize(BB2DbObjects.RulesSkillListing.CacheFind(), (lambda x: x.ID))
        return

    @classmethod
    def GetPlayerInfos(cls, idPlayer, withStats=False):
        player = BB2DbObjects.PlayerListing.FindFirst(ID=idPlayer)
        if player == None:
            return
        else:
            lstSkills = BB2DbObjects.PlayerSkills.Find(idPlayerListing=idPlayer)
            lstCasualties = BB2DbObjects.PlayerCasualties.Find(idPlayerListing=idPlayer)
            dboPlayerType = PlayerType.CacheFindFirst(ID=player.idPlayerTypes)
            dicPlayer = {}
            dicPlayer['player'] = player
            dicPlayer['skills'] = lstSkills
            dicPlayer['casualties'] = lstCasualties
            dicPlayer['playerType'] = dboPlayerType
            if withStats:
                dicPlayer['statistics'] = BB2DbObjects.StatisticsPlayers.Find(idPlayerListing=idPlayer)
            else:
                dicPlayer['statistics'] = []
            query = 'SELECT sellPrice FROM bb_league_marketplace_sellings WHERE idPlayer=%s'
            dicPlayer['sellingPrice'] = DBManager().QueryOneValue(query, idPlayer, 0)
            return dicPlayer

    @classmethod
    def GetPlayerInfosMsg(cls, idPlayer, withStats=False):
        dicPlayerInfos = cls.GetPlayerInfos(idPlayer, withStats)
        if dicPlayerInfos == None:
            raise PyLobbyException(BBExceptionDesc.PlayerNotFound)
        msgPlayerInfos = BB2Data.PlayerInfos()
        ShardingManager.AssignToSharded(dicPlayerInfos['player'], msgPlayerInfos.player.row)
        msgPlayerInfos.skills = [ x.idSkillListing for x in dicPlayerInfos['skills'] ]
        msgPlayerInfos.casualties = [ x.idPlayerCasualtyTypes for x in dicPlayerInfos['casualties'] ]
        msgPlayerInfos.sellingPrice = dicPlayerInfos.get('sellingPrice', 0)

        def EnsurePlayerStatistics(category, playerStatsCategories):
            if category not in playerStatCategories:
                msgStats = BB2Data.StatisticsPlayer()
                msgStats.row.idPlayerListing = dicPlayerInfos['player'].ID
                msgStats.category = category
                msgPlayerInfos.statistics.append(msgStats)

        if withStats:
            playerStatCategories = []
            for stat in dicPlayerInfos['statistics']:
                msgStats = BB2Data.StatisticsPlayer()
                ShardingManager.AssignToSharded(stat, msgStats.row)
                msgStats.category = stat.category
                msgPlayerInfos.statistics.append(msgStats)
                playerStatCategories.append(stat.category)

            EnsurePlayerStatistics('CARREER', playerStatCategories)
            EnsurePlayerStatistics('CURRENTCOMPETITION', playerStatCategories)
        return msgPlayerInfos

    def AddSkill(self, skillId):
        playerSkill = BB2DbObjects.PlayerSkills()
        playerSkill.idPlayerListing = self.ID
        playerSkill.idSkillListing = skillId
        playerSkill.Save()
        return True

    def CanHaveSkill(self, idSkill, **kwargs):
        useCache = kwargs.get('useCache', True)
        raiseException = kwargs.get('raiseException', False)
        skill = BB2DbObjects.RulesSkillListing.CacheFindFirst(ID=idSkill) if useCache else BB2DbObjects.RulesSkillListing.FindFirst(ID=idSkill)
        if skill == None:
            return False
        else:
            lstIdSkill = self.GetSkillIds()
            playerBaseSkills = self.GetBaseSkillIds(useCache)
            allPlayerSkills = lstIdSkill + playerBaseSkills
            if Skill.IsCharac(idSkill):
                lstCasualtyObj = self.GetCasualtiesDbo()
                dicCharacsIncrease = GetDicCharacsModifiers()
                for idOwnedSkills in lstIdSkill:
                    if Skill.IsCharac(idOwnedSkills):
                        dicCharacsIncrease[DicSkillToCharacs[idOwnedSkills]] += 1

                for casObj in lstCasualtyObj:
                    if casObj.IdCaracs != None and casObj.IdCaracs != 0:
                        dicCharacsIncrease[casObj.IdCaracs] -= 1

                if dicCharacsIncrease[DicSkillToCharacs[idSkill]] >= 2:
                    if raiseException:
                        raise PyLobbyException(BBExceptionDesc.Gui_Warning_TwoPoints_Skill)
                    return False
                if idSkill == ESkillListing.IncreaseAgility and self.characsAgility + dicCharacsIncrease[DicSkillToCharacs[ESkillListing.IncreaseAgility]] >= MaxCharacValue:
                    if raiseException:
                        raise PyLobbyException(BBExceptionDesc.Gui_Warning_MaxTen_Skill)
                    return False
                if idSkill == ESkillListing.IncreaseArmour and self.characsArmourValue + dicCharacsIncrease[DicSkillToCharacs[ESkillListing.IncreaseArmour]] >= MaxCharacValue:
                    if raiseException:
                        raise PyLobbyException(BBExceptionDesc.Gui_Warning_MaxTen_Skill)
                    return False
                if idSkill == ESkillListing.IncreaseMovement and self.characsMovementAllowance + dicCharacsIncrease[DicSkillToCharacs[ESkillListing.IncreaseMovement]] >= MaxCharacValue:
                    if raiseException:
                        raise PyLobbyException(BBExceptionDesc.Gui_Warning_MaxTen_Skill)
                    return False
                if idSkill == ESkillListing.IncreaseStrength and self.characsStrength + dicCharacsIncrease[DicSkillToCharacs[ESkillListing.IncreaseStrength]] >= MaxCharacValue:
                    if raiseException:
                        raise PyLobbyException(BBExceptionDesc.Gui_Warning_MaxTen_Skill)
                    return False
                return True
            if idSkill in allPlayerSkills:
                if raiseException:
                    raise PyLobbyException(BBExceptionDesc.Gui_Warning_AlreadyHave_Skill)
                return False
            hasGrab = ESkillListing.Grab in allPlayerSkills
            hasFrenzy = ESkillListing.Frenzy in allPlayerSkills
            if idSkill == ESkillListing.Grab and hasFrenzy:
                if raiseException:
                    raise PyLobbyException(BBExceptionDesc.Gui_Warning_Forbidden_Skill)
                return False
            if idSkill == ESkillListing.Frenzy and hasGrab:
                if raiseException:
                    raise PyLobbyException(BBExceptionDesc.Gui_Warning_Forbidden_Skill)
                return False
            found = 0
            if useCache:
                found = BB2DbObjects.RulesPlayerTypeSkillCategoriesNormal.CacheCount(IdSkillCategories=skill.IdSkillCategories, IdPlayerTypes=self.idPlayerTypes)
                found += BB2DbObjects.RulesPlayerTypeSkillCategoriesDouble.CacheCount(IdSkillCategories=skill.IdSkillCategories, IdPlayerTypes=self.idPlayerTypes)
            else:
                found = BB2DbObjects.RulesPlayerTypeSkillCategoriesNormal.Count(IdSkillCategories=skill.IdSkillCategories, IdPlayerTypes=self.idPlayerTypes)
                found += BB2DbObjects.RulesPlayerTypeSkillCategoriesDouble.Count(IdSkillCategories=skill.IdSkillCategories, IdPlayerTypes=self.idPlayerTypes)
            return bool(found)

    def GetLearnableSkills(self, **kwargs):
        if self.nbLevelsUp == 0:
            return []
        else:
            useCache = kwargs.get('useCache', True)
            batchOperationCache = kwargs.get('batchOperationCache', None)
            hasDouble = False
            if self.levelUpRollResult == self.levelUpRollResult2:
                hasDouble = True
            baseSkillIds = None
            if batchOperationCache != None:
                idCategories = batchOperationCache['RulesPlayerTypeSkillCategoriesNormal'].get(self.idPlayerTypes)[:]
                if hasDouble:
                    idCategories += batchOperationCache['RulesPlayerTypeSkillCategoriesDouble'].get(self.idPlayerTypes)
                baseSkillIds = batchOperationCache['RulesPlayerTypeSkills'].get(self.idPlayerTypes, [])
            else:
                categories = BB2DbObjects.RulesPlayerTypeSkillCategoriesNormal.Find(IdPlayerTypes=self.idPlayerTypes)
                if hasDouble:
                    categories += BB2DbObjects.RulesPlayerTypeSkillCategoriesDouble.Find(IdPlayerTypes=self.idPlayerTypes)
                idCategories = [ x.IdSkillCategories for x in categories ]
                baseSkillIds = self.GetBaseSkillIds(useCache)
            playerSkillIds = set(baseSkillIds + self.GetSkillIds())
            if batchOperationCache != None:
                skills = batchOperationCache['RulesSkillListing']
            else:
                skills = BB2DbObjects.RulesSkillListing.CacheFind()
            learnableSkills = []
            canHaveGrab = True
            canHaveFrenzy = False
            for idPlayerSkill in playerSkillIds:
                if idPlayerSkill == ESkillListing.Grab:
                    canHaveFrenzy = False
                    break
                if idPlayerSkill == ESkillListing.Frenzy:
                    canHaveGrab = False
                    break

            for skill in skills:
                if skill.IdSkillCategories in idCategories and skill.ID not in playerSkillIds:
                    if skill.ID == ESkillListing.Grab and not canHaveGrab:
                        continue
                    if skill.ID == ESkillListing.Frenzy and not canHaveFrenzy:
                        continue
                    learnableSkills.append(skill.ID)

            if self.levelUpRollResult + self.levelUpRollResult2 in (10, 11, 12):
                lstCasualtyObj = self.GetCasualtiesDbo()
                dicCharacsIncrease = GetDicCharacsModifiers()
                for idSkill in playerSkillIds:
                    if idSkill in [ESkillListing.IncreaseStrength, ESkillListing.IncreaseAgility, ESkillListing.IncreaseArmour, ESkillListing.IncreaseMovement]:
                        dicCharacsIncrease[DicSkillToCharacs[idSkill]] += 1

                for casObj in lstCasualtyObj:
                    if casObj.IdCaracs != None and casObj.IdCaracs != 0:
                        dicCharacsIncrease[casObj.IdCaracs] -= 1

                if self.levelUpRollResult + self.levelUpRollResult2 == 10:
                    if dicCharacsIncrease[ECharacs.AV] < 2:
                        learnableSkills.append(ESkillListing.IncreaseArmour)
                    if dicCharacsIncrease[ECharacs.MV] < 2:
                        learnableSkills.append(ESkillListing.IncreaseMovement)
                else:
                    if self.levelUpRollResult + self.levelUpRollResult2 == 11:
                        if dicCharacsIncrease[ECharacs.AG] < 2:
                            learnableSkills.append(ESkillListing.IncreaseAgility)
                    elif self.levelUpRollResult + self.levelUpRollResult2 == 12:
                        if dicCharacsIncrease[ECharacs.ST] < 2:
                            learnableSkills.append(ESkillListing.IncreaseStrength)
            return learnableSkills

    def HasSkill(self, idSkill):
        if BB2DbObjects.PlayerSkills.Count(idPlayerListing=self.ID, idSkillListing=idSkill) > 0:
            return True
        return False

    def ProcessAging(self):
        self.age += 1
        GetLog(ELogs.General).info('Player.ProcessAging : %d New Age : %d', self.ID, self.age)
        retirementParams = ServerConfig.Config().GetCachedValue('PlayerRetirementParams', [{'age': 31, 'percentChanceRetirement': 40}, {'age': 32, 'percentChanceRetirement': 60}, {'age': 33, 'percentChanceRetirement': 100}])
        retirementParams.sort(key=(lambda x: x['age']))
        for i, param in enumerate(retirementParams):
            if self.age == param['age'] or self.age >= param['age'] and i + 1 == len(retirementParams):
                roll = random.randint(0, 100)
                if roll < param['percentChanceRetirement']:
                    GetLog(ELogs.General).info('Player.ProcessAging : %d - Player retiring - param matched : %d', self.ID, param['age'])
                    self.retired = 1
                break

        self.nbMatchsSinceAgeRoll = 0

    @classmethod
    def GetLevelReached(cls, experience):
        iReachedLevel = 1
        for level in cls.DicLevels.keys():
            levelThreshold = cls.DicLevels[level]
            if experience > levelThreshold and level + 1 > iReachedLevel:
                iReachedLevel = level + 1

        return iReachedLevel

    @classmethod
    def GetXpForLevel(cls, level):
        if level == 1:
            return 0
        return cls.DicLevels.get(max(0, level - 1), 0) + 1

    def EarnExperience(self, experience):
        reachedLevel = self.GetLevelReached(experience + self.experience)
        levelDiff = max(reachedLevel - self.idPlayerLevels, 0)
        if levelDiff > 0:
            self.nbLevelsUp = self.nbLevelsUp + levelDiff
            self.idPlayerLevels = reachedLevel
            self.levelUpRollResult = random.randint(1, 6)
            self.levelUpRollResult2 = random.randint(1, 6)
        self.experience = self.experience + experience

    def DeleteSkills(self):
        DBManager().Query('DELETE FROM bb_player_skills WHERE idPlayerListing=%s', self.ID)

    def GetSkillIds(self):
        if hasattr(self, '_skillIds'):
            return getattr(self, '_skillIds')
        rows = DBManager().Query('SELECT idSkillListing as ID FROM bb_player_skills WHERE idPlayerListing=%s', self.ID)
        return [ row['ID'] for row in rows ]

    def GetBaseSkillIds(self, useCache=True):
        return PlayerType.GetBaseSkills(self.idPlayerTypes, useCache)

    def GetSkillsDbo(self):
        lstIds = self.GetSkillIds()
        skillsDbos = []
        for idSkill in lstIds:
            if self._dicSkillsDbo.has_key(idSkill):
                skillsDbos.append(self._dicSkillsDbo[idSkill][0])

        return skillsDbos

    def Suspend(self):
        self.matchSuspended = 1

    def Kill(self):
        self.dead = 1

    def ComputeValue(self, **kwargs):
        useCache = kwargs.get('useCache', True)
        batchOperationCache = kwargs.get('batchOperationCache', None)
        if batchOperationCache != None and batchOperationCache.has_key('RulesPlayerTypes'):
            playerType = batchOperationCache['RulesPlayerTypes'][self.idPlayerTypes]
        elif useCache:
            playerType = BB2DbObjects.RulesPlayerTypes.CacheFindFirst(ID=self.idPlayerTypes)
        else:
            playerType = BB2DbObjects.RulesPlayerTypes.FindFirst(ID=self.idPlayerTypes)
        if playerType == None:
            GetLog(ELogs.General).error('Player.ComputeValue - Error Loading player type id : %d' % self.idPlayerTypes)
            return False
        else:
            playerValue = playerType.Price
            self._dboSkills = self.GetSkillsDbo()
            if batchOperationCache != None and batchOperationCache.has_key('RulesPlayerTypeSkillCategoriesNormal'):
                lstPlayerSkillsCatNormal = batchOperationCache['RulesPlayerTypeSkillCategoriesNormal'].get(self.idPlayerTypes)
                lstPlayerSkillsCatDouble = batchOperationCache['RulesPlayerTypeSkillCategoriesDouble'].get(self.idPlayerTypes)
            elif useCache:
                lstPlayerSkillsCatNormal = [ x.IdSkillCategories for x in BB2DbObjects.RulesPlayerTypeSkillCategoriesNormal.CacheFind(IdPlayerTypes=self.idPlayerTypes) ]
                lstPlayerSkillsCatDouble = [ x.IdSkillCategories for x in BB2DbObjects.RulesPlayerTypeSkillCategoriesDouble.CacheFind(IdPlayerTypes=self.idPlayerTypes) ]
            else:
                lstPlayerSkillsCatNormal = [ x.IdSkillCategories for x in BB2DbObjects.RulesPlayerTypeSkillCategoriesNormal.Find(IdPlayerTypes=self.idPlayerTypes) ]
                lstPlayerSkillsCatDouble = [ x.IdSkillCategories for x in BB2DbObjects.RulesPlayerTypeSkillCategoriesDouble.Find(IdPlayerTypes=self.idPlayerTypes) ]
            for skill in self._dboSkills:
                GetLog(ELogs.General).debug('In Player.ComputeValue. Processing : %d ', skill.ID)
                if skill.ID == ESkillListing.IncreaseStrength:
                    playerValue = playerValue + STValue
                elif skill.ID == ESkillListing.IncreaseAgility:
                    playerValue = playerValue + AGValue
                elif skill.ID == ESkillListing.IncreaseMovement:
                    playerValue = playerValue + MVorAVValue
                elif skill.ID == ESkillListing.IncreaseArmour:
                    playerValue = playerValue + MVorAVValue
                if skill.IdSkillCategories in lstPlayerSkillsCatNormal:
                    playerValue = playerValue + SkillValue
                elif skill.IdSkillCategories in lstPlayerSkillsCatDouble:
                    playerValue = playerValue + DoubleSkillValue

            playerValue = playerValue / 1000
            self.value = playerValue
            return True

    def DeleteCasualties(self, givenCursor=None):
        DBManager().Query('DELETE FROM bb_player_casualties WHERE idPlayerListing = %s', self.ID)

    def Reset(self):
        self.DeleteSkills()
        self.DeleteCasualties()
        self.dead = 0
        self.matchSuspended = 0
        self.nbLevelsUp = 0
        self.idPlayerLevels = 1
        self.ComputeValue()
        self.Save()

    def Delete(self):
        self.DeleteSkills()
        self.DeleteCasualties()
        self.DeleteStatistics()
        BB2DbObjects.PlayerListing.Delete(self)

    def DeleteStatistics(self):
        DBManager().Query('DELETE FROM bb_statistics_players WHERE idPlayerListing = %s', self.ID)

    def GetCasualtiesIds(self):
        return [ x.idPlayerCasualtyTypes for x in BB2DbObjects.PlayerCasualties.Find(idPlayerListing=self.ID) ]

    def GetCasualtiesDbo(self):
        if hasattr(self, '_dboCasualties'):
            return getattr(self, '_dboCasualties')
        playerCasualtiesId = self.GetCasualtiesIds()
        dboCasualties = BB2DbObjects.RulesPlayerCasualtyTypes.Find(ID=playerCasualtiesId)
        result = []
        for idCas in playerCasualtiesId:
            for dboCas in dboCasualties:
                if dboCas.ID == idCas:
                    result.append(dboCas)

        return result

    def GetCharacValue(self, idCarac):
        mapping = {ECharacs.AV: 'characsArmourValue', ECharacs.MV: 'characsMovementAllowance', ECharacs.ST: 'characsStrength', ECharacs.AG: 'characsAgility'}
        if mapping.has_key(idCarac):
            return getattr(self, mapping[idCarac], 0)
        return 0

    def AddCasualty(self, idCasualty, **kwargs):
        addCasualty = True
        if ServerConfig.Config().GetCachedValue('BBCapCasualtiesBySkippingThem', True):
            addReplacementCasualty = ServerConfig.Config().GetCachedValue('BBCapCasualtiesWithReplacement', False)
            dicCasualties = kwargs.get('dicCasualties', None)
            if dicCasualties == None:
                dicCasualties = GetDicDboCasualtiesById()
            dboCasToAdd = dicCasualties.get(idCasualty)
            characModifier = 0
            if dboCasToAdd == None:
                return
            if dboCasToAdd.IdCaracs != None and dboCasToAdd.IdCaracs != 0:
                idCaracImpacted = dboCasToAdd.IdCaracs
                playerSkillIds = self.GetSkillIds()
                playerCasualties = self.GetCasualtiesDbo()
                for idSkill in playerSkillIds:
                    idCharac = DicSkillToCharacs.get(idSkill, 0)
                    if idCharac == idCaracImpacted:
                        characModifier += 1

                for dboCas in playerCasualties:
                    if dboCas.IdCaracs == idCaracImpacted:
                        characModifier -= 1

                if characModifier <= -2:
                    GetLog(ELogs.General).info('AddCasualty player %d - skip Charac Cas on carac modifier < 2', self.ID)
                    if addReplacementCasualty:
                        idCasualty = random.choice(LightMngCasualties)
                    else:
                        addCasualty = False
                else:
                    characValue = self.GetCharacValue(idCaracImpacted)
                    if characValue + characModifier - 1 < 1:
                        GetLog(ELogs.General).info('AddCasualty player %d - skip Chara Cas on carac value < 1', self.ID)
                        if addReplacementCasualty:
                            idCasualty = random.choice(LightMngCasualties)
                        else:
                            addCasualty = False
        if addCasualty:
            playerCas = BB2DbObjects.PlayerCasualties()
            playerCas.idPlayerListing = self.ID
            playerCas.idPlayerCasualtyTypes = idCasualty
            playerCas.Save()
            return True
        else:
            return False

    def CanTeamOverrideLevelUp(self, teamClass=TeamListing):
        team = teamClass()
        if self.idPlayerLevels >= 7:
            return False
        if not team.Load(self.idTeamListing):
            raise PyLobbyException(BBExceptionDesc.TeamNotFound)
        if team.IsCustomPhase():
            return True
        return False

    def CleanupLightCasulaties(self):
        casualties = BB2DbObjects.PlayerCasualties.Find(idPlayerListing=self.ID)
        for casualty in casualties:
            if casualty.idPlayerCasualtyTypes in LightCasualties:
                casualty.Delete()

    def LevelUp(self, idSkill, **kwargs):
        GetLog(ELogs.General).debug('Player.LevelUp Player:%d', self.ID)
        useCache = kwargs.get('useCache', True)
        dboSkill = kwargs.get('dboSkill', None)
        recomputeAndSave = kwargs.get('recomputeAndSave', True)
        checkCanHaveSkill = kwargs.get('checkCanHaveSkill', True)
        if self.nbLevelsUp <= 0 and not self.CanTeamOverrideLevelUp():
            raise PyLobbyException(BBExceptionDesc.PlayerSkillError)
        if dboSkill != None:
            skill = dboSkill
        else:
            skill = BB2DbObjects.RulesSkillListing.CacheFindFirst(ID=idSkill)
        if skill == None:
            raise PyLobbyException(BBExceptionDesc.PlayerSkillError)
        if checkCanHaveSkill:
            if not self.CanHaveSkill(idSkill, useCache=useCache, raiseException=True):
                raise PyLobbyException(BBExceptionDesc.PlayerSkillError)
        iMinDiceValue = 0
        if skill.DataConstant == 'IncreaseStrength':
            iMinDiceValue = DiceIncreaseST
        elif skill.DataConstant == 'IncreaseAgility':
            iMinDiceValue = DiceIncreaseAG
        elif skill.DataConstant == 'IncreaseMovement' or skill.DataConstant == 'IncreaseArmour':
            iMinDiceValue = DiceIncreaseARorMV
        if self.levelUpRollResult + self.levelUpRollResult2 < iMinDiceValue and not self.CanTeamOverrideLevelUp():
            raise PyLobbyException(BBExceptionDesc.PlayerSkillError)
        if not self.AddSkill(idSkill):
            raise PyLobbyException(BBExceptionDesc.PlayerSkillError)
        if not self.CanTeamOverrideLevelUp():
            self.nbLevelsUp = self.nbLevelsUp - 1
            if self.nbLevelsUp > 0:
                self.levelUpRollResult = random.randint(1, 6)
                self.levelUpRollResult2 = random.randint(1, 6)
            else:
                self.levelUpRollResult = 0
                self.levelUpRollResult2 = 0
        else:
            self.nbLevelsUp = self.nbLevelsUp - 1
        if recomputeAndSave:
            self.ComputeValue(useCache=useCache)
            self.Save()
        return

    def GetPrice(self):
        return self.value * 1000


class StatisticsPlayer(BB2DbObjects.StatisticsPlayers):
    StatsOmmitedFields = [
     'ID', 'category', 'idPlayerListing']
    XpPerInterception = 2
    XpPerMVP = 5
    XpPerPassingCompletion = 1
    XpPerCasualty = 2
    XpPerTouchdown = 3

    def EarnedExperience(self):
        return self.XpPerInterception * self.inflictedInterceptions + self.XpPerMVP * min(self.MVP, 1) + self.XpPerPassingCompletion * self.inflictedPasses + self.XpPerCasualty * self.inflictedCasualties + self.XpPerTouchdown * self.inflictedTouchdowns

    def CleanupLightCasulaties(self):
        lstCasualties = BB2DbObjects.PlayerCasualties.Find(idPlayerListing=self.ID)
        for playerCasualty in lstCasualties:
            if playerCasualty.idPlayerCasualtyTypes in LightCasualties:
                playerCasualty.Delete()

    def AddMatchStats(self, stats, **kwstats):
        attrListToSum = [ field for field in self.__dict__.keys() if field not in self.StatsOmmitedFields ]
        for attr in attrListToSum:
            if hasattr(stats, attr):
                setattr(self, attr, getattr(self, attr) + getattr(stats, attr))


class PlayerType(BB2DbObjects.RulesPlayerTypes):

    @classmethod
    def GetPrice(cls, idPlayerTypes):
        playerType = PlayerType.CacheFindFirst(ID=idPlayerTypes)
        if playerType != None:
            return playerType.Price
        else:
            return

    @classmethod
    def GetBaseSkills(cls, idPlayerTypes, useCache=True):
        dbos = BB2DbObjects.RulesPlayerTypeSkills.CacheFind(IdPlayerTypes=idPlayerTypes) if useCache else BB2DbObjects.RulesPlayerTypeSkills.Find(IdPlayerTypes=idPlayerTypes)
        return [ dbo.IdSkillListing for dbo in dbos ]


class MatchRecord(BB2DbObjectsImpl.MatchRecords):
    ComplementaryStats = [
     'Passes', 'Catches', 'Interceptions', 'Touchdowns', 'Tackles', 
     'MetersRunning', 'MetersPassing']

    def GetTeamStats(self, prefix):
        if prefix not in ('home', 'away'):
            raise Exception('BadPrefix')
        otherTeamPrefix = 'away'
        if prefix == 'away':
            otherTeamPrefix = 'home'
        teamStats = StatisticsTeam()
        for key, value in self.__dict__.items():
            if key.startswith(prefix):
                fieldName = key.replace(prefix, '', 1)
                fieldName = '%s%s' % (fieldName[0].lower(), fieldName[1:])
                setattr(teamStats, fieldName, value)
            else:
                otherTeamInflictedPrefix = '%s%s' % (otherTeamPrefix, 'Inflicted')
                if key.startswith(otherTeamInflictedPrefix):
                    suffix = key[len(otherTeamInflictedPrefix):len(key)]
                    if suffix in self.ComplementaryStats:
                        sustainedStat = 'sustained%s' % suffix
                        setattr(teamStats, sustainedStat, value)

        teamStats.wins = 0
        teamStats.draws = 0
        teamStats.loss = 0
        thisTeamScore = 0
        otherTeamScore = 0
        if prefix == 'home':
            thisTeamScore = self.homeScore
            otherTeamScore = self.awayScore
        else:
            thisTeamScore = self.awayScore
            otherTeamScore = self.homeScore
        if thisTeamScore > otherTeamScore:
            teamStats.wins = 1
        elif thisTeamScore < otherTeamScore:
            teamStats.loss = 1
        else:
            teamStats.draws = 1
        teamStats.matchPlayed = 1
        return teamStats


def TeamAlreadyExist(name):
    nbTeams = BB2DbObjects.TeamListing.Count(name=name, deleted=0)
    if nbTeams > 0:
        return True
    return False


def CreateTeam(idCoach, dboTeam):
    if len(dboTeam.name) < TeamNameMinLength:
        raise PyLobbyException(BBExceptionDesc.TeamNameTooShort)
    if len(dboTeam.name) > TeamNameMaxLength:
        raise PyLobbyException(BBExceptionDesc.TeamNameTooLong)
    nbTeams = BB2DbObjects.TeamListing.Count(name=dboTeam.name, deleted=0)
    if nbTeams > 0:
        raise PyLobbyException(BBExceptionDesc.TeamNameAlreadyUsed)
    nbTeamsCreated = BB2DbObjects.TeamListing.Count(idCoach=idCoach, deleted=0)
    if nbTeamsCreated >= ServerConfig.Config().GetCachedValue('BBMaxTeamPerCoach', 8):
        raise PyLobbyException(BBExceptionDesc.TooManyTeams)
    nbRaces = BB2DbObjects.RulesRaces.CacheCount(ID=dboTeam.IdRaces)
    if nbRaces <= 0:
        raise PyLobbyException(BBExceptionDesc.RaceInvalid)
    if dboTeam.IdRaces in [ERaces.MercenaryAristo,
     ERaces.MercenaryChaos,
     ERaces.MercenaryChaosGods,
     ERaces.MercenaryEasterners,
     ERaces.MercenaryElf,
     ERaces.MercenaryExplorers,
     ERaces.MercenaryGoodGuys,
     ERaces.MercenaryHuman,
     ERaces.MercenarySavage,
     ERaces.MercenaryStunty,
     ERaces.MercenaryUndead,
     ERaces.Khorne]:
        dboTeam.flags |= BB2Data.ETeamFlags.Mercenary
    dboTeam.idCoach = idCoach
    dboTeam.idOwner = idCoach
    dboTeam.value = 0
    dboTeam.popularity = 0
    if dboTeam.flags & BB2Data.ETeamFlags.Custom == BB2Data.ETeamFlags.Custom:
        dboTeam.cash = 0
    else:
        dboTeam.cash = CashOnTeamCreate
    dboTeam.cheerleaders = 0
    dboTeam.balms = 0
    dboTeam.apothecary = 0
    dboTeam.rerolls = 0
    dboTeam.edited = 0
    dboTeam.online = 1
    dboTeam.active = 1
    dboTeam.assistantCoaches = 0
    dboTeam.stadiumLevel = 1
    dboTeam.Save()
    if dboTeam.IdRaces == ERaces.Undead or dboTeam.IdRaces == ERaces.Necromantic or dboTeam.IdRaces == ERaces.MercenaryUndead:
        dboTeam.AddNecromancerCard(1)
        dboTeam.Save()
    return dboTeam


def PlayerAddCasualty(idCoach, idPlayer, idCasualty, teamClass=TeamListing):
    player = PlayerListing()
    if not player.Load(idPlayer):
        GetLog(ELogs.General).error('In PlayerLevelUp - Player not found :%d' % idPlayer)
        raise PyLobbyException(BBExceptionDesc.PlayerNotFound)
    team = teamClass()
    if not team.Load(player.idTeamListing):
        raise PyLobbyException(BBExceptionDesc.TeamNotFound)
    if not idCoach == team.idCoach:
        if DBManager().GetStoreName() != 'Campaign':
            raise PyLobbyException(BBExceptionDesc.InsuffisentRights)
    player.AddCasualty(idCasualty)
    team.ComputeValue()
    team.UpdateLevelUpPending(False)
    team.Save()
    playerInfos = PlayerListing.GetPlayerInfos(idPlayer)
    return (
     team, playerInfos)


def PlayerLevelUp(idCoach, idPlayer, idSkill, teamClass=TeamListing):
    player = PlayerListing()
    if not player.Load(idPlayer):
        GetLog(ELogs.General).error('In PlayerLevelUp - Player not found :%d' % idPlayer)
        raise PyLobbyException(BBExceptionDesc.PlayerNotFound)
    team = teamClass()
    if not team.Load(player.idTeamListing):
        raise PyLobbyException(BBExceptionDesc.TeamNotFound)
    if team.HasGameInvitationPending():
        raise PyLobbyException(BBExceptionDesc.TeamHasBeenInvited)
    if not idCoach == team.idCoach:
        if DBManager().GetStoreName() != 'Campaign':
            raise PyLobbyException(BBExceptionDesc.InsuffisentRights)
    player.LevelUp(idSkill)
    team.ComputeValue()
    team.UpdateLevelUpPending(False)
    team.Save()
    playerInfos = PlayerListing.GetPlayerInfos(idPlayer)
    return (
     team, playerInfos)


def LoadTeamAndCheckOwner(idTeam, idCoach, teamClass=TeamListing):
    team = teamClass()
    if not team.Load(idTeam):
        raise PyLobbyException(BBExceptionDesc.TeamNotFound)
    if not team.idCoach == idCoach:
        if DBManager().GetStoreName() != 'Campaign':
            raise PyLobbyException(BBExceptionDesc.InsuffisentRights)
        elif team.predefined == 1:
            raise PyLobbyException(BBExceptionDesc.InsuffisentRights)
    return team


def CheckTeamExistenceAndOwner(idTeam, idCoach):
    idOwner = DBManager().QueryOneValue(' SELECT idCoach FROM bb_team_listing WHERE ID=%s', idTeam, 0)
    if idOwner == 0:
        return False
    if idOwner != idCoach:
        return False
    return True


def CheckNoLevelUpPending(idTeam):
    levelupPending = DBManager().QueryOneValue(' SELECT levelupPending FROM bb_team_listing WHERE ID=%s', idTeam, 0)
    if levelupPending > 0:
        return False
    return True


def GetDicDboCasualtiesById():
    dboCasualties = BB2DbObjects.RulesPlayerCasualtyTypes.CacheFind()
    dicCasualties = {}
    for dboCas in dboCasualties:
        dicCasualties[dboCas.ID] = dboCas

    return dicCasualties


def GetDicCharacsModifiers():
    return {ECharacs.AG: 0, ECharacs.MV: 0, ECharacs.ST: 0, ECharacs.AV: 0}


LstMatchSuspendedCasualties = [
 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17]
LightCasualties = [1, 2, 3, 4, 5, 6, 7, 8, 9]
CasualtyDead = 18
CasualtyCommotion = 1
IdJourneyMan = 0
IdFreeJourneyMan = -1

def ProcessPostMatchTeamEvolution(teamResult, matchRecord, playerLookupOnNumber=False, **kwArgs):
    competitionFlags = matchRecord.competitionFlags
    hasAging = kwArgs.get('hasAging', competitionFlags & BB2Data.ELeagueFlags.NoAging == 0)
    sendRetirementNotif = kwArgs.get('sendRetirementNotif', True)
    rosterPlayers = kwArgs.get('rosterPlayers', None)
    fillRosterPlayers = rosterPlayers != None
    bIsModeResurrection = competitionFlags & BB2Data.ELeagueFlags.ModeResurrection != 0
    GetLog(ELogs.General).info('ProcessPostMatchTeamEvolution Team ID :%d Aging : %s', teamResult.idTeam, hasAging)
    team = TeamListing()
    if not team.Load(teamResult.idTeam):
        GetLog(ELogs.General).error('ProcessPostMatchTeamEvolution Team ID Not Found :%d', teamResult.idTeam)
        return
    else:
        if team.deleted == 1:
            GetLog(ELogs.General).error('ProcessPostMatchTeamEvolution Skipping deleted team :%d', teamResult.idTeam)
            return
        if team.predefined == 1:
            GetLog(ELogs.General).error('ProcessPostMatchTeamEvolution Skipping predefined team :%d', teamResult.idTeam)
            return
        GetLog(ELogs.General).info('Team %d Updating cash after match. Cash earned : %d - Cash Spent inducements : %d Spirraling : %d', teamResult.idTeam, teamResult.cashEarned, teamResult.cashSpentInducements, teamResult.spirallingExpenses)
        if not bIsModeResurrection:
            earnedCash = teamResult.cashEarned - teamResult.cashSpentInducements - teamResult.spirallingExpenses
            team.cash = Utils.Clamp(team.cash + earnedCash, 0, GetTeamMaxGold())
            if earnedCash > 0 and team.idCoach != 0:
                BB2Achievements.RunAchievementHandlers(team.idCoach, 'BB2Achievements.HandlerTeamCharacs', (team, ['minGold']), None)
        if not bIsModeResurrection:
            oldPop = team.popularity
            newPop = Utils.Clamp(team.popularity + teamResult.popularityGain, 0, MaxPopularity)
            diffPop = newPop - oldPop
            try:
                if diffPop > 0:
                    team.AddFFCard(diffPop)
                    if team.idCoach != 0:
                        import CardsManagement
                        popCard = CardsManagement.GetCardDataByNameFromCache('FanFactor')
                        if popCard != None:
                            BB2Achievements.RunAchievementHandlers(team.idCoach, 'BB2Achievements.HandlerTeamCardsPossesion', (team.ID, [popCard['ID']], [popCard['IdCardTypes']]), None)
                        else:
                            GetLog(ELogs.General).error('ProcessPostMatchTeamEvolution Error No FF card Found')
                elif diffPop < 0:
                    team.RemoveFFCard(-diffPop)
                if diffPop != 0:
                    team.ComputeLrb6Items()
            except Exception as e:
                GetLog(ELogs.General).error('ProcessPostMatchTeamEvolution Error processing FF diff :%s' % str(e))

        team.Save()
        DBManager().Query('UPDATE bb_player_listing SET matchSuspended=0 WHERE idTeamListing=%s', teamResult.idTeam)
        if len(LightCasualties) > 0:
            query = 'DELETE FROM bb_player_casualties WHERE idPlayerListing \n                   IN (SELECT ID FROM bb_player_listing WHERE idTeamListing=%d) AND idPlayerCasualtyTypes IN (%s)' % (teamResult.idTeam, Utils.GetStrSepList(LightCasualties))
            DBManager().Query(query)
        updatePlayerCount = False
        dicCasualties = None
        dboTeamPlayers = PlayerListing.Find(idTeamListing=teamResult.idTeam)
        if fillRosterPlayers:
            rosterPlayers = list(player for player in dboTeamPlayers)
        dicPlayerById = {x['ID']: x for x in dboTeamPlayers}
        dicPlayersByNumber = {x['number']: x for x in dboTeamPlayers}
        for playerResult in teamResult.playerResults:
            if playerResult.playerData.contract != RulesEngineData.EContract.RosterMember:
                GetLog(ELogs.General).info('ProcessPostMatchTeamEvolution Skipping Evolution process on non roster member Team %d Player Number : %d', teamResult.idTeam, playerResult.playerData.number)
                continue
            bPlayerChanged = False
            player = None
            if playerLookupOnNumber:
                playerNumber = playerResult.playerData.number
                player = dicPlayersByNumber.get(playerNumber, None)
                if player == None:
                    GetLog(ELogs.General).error('ProcessPostMatchTeamEvolution Number %d not found on Team Id:%d' % (playerResult.statistics.idPlayerListing, teamResult.idTeam))
                    continue
            else:
                player = dicPlayerById.get(playerResult.statistics.idPlayerListing, None)
                if player == None:
                    GetLog(ELogs.General).error('ProcessPostMatchTeamEvolution Player ID Not Found :%d' % playerResult.statistics.idPlayerListing)
                    continue
                if player.idTeamListing != teamResult.idTeam:
                    GetLog(ELogs.General).error('ProcessPostMatchTeamEvolution Player ID %d not belonging to Team Id:%d' % (playerResult.statistics.idPlayerListing, teamResult.idTeam))
                    continue

            def handleCasualty(casualty, dicCasualties):
                if casualty > 0:
                    if not casualty == CasualtyCommotion:
                        if player.AddCasualty(casualty, dicCasualties=dicCasualties):
                            bPlayerChanged = True
                        if casualty in LstMatchSuspendedCasualties:
                            player.matchSuspended = 1
                    if casualty == CasualtyDead:
                        player.dead = 1
                        bPlayerChanged = True

            if playerResult.casualty1 != 0:
                if dicCasualties == None:
                    dicCasualties = GetDicDboCasualtiesById()
            if not bIsModeResurrection:
                handleCasualty(playerResult.casualty1, dicCasualties)
                handleCasualty(playerResult.casualty2, dicCasualties)
            if not player.dead == 1:
                statistics = StatisticsPlayer()
                Utils.Assign(playerResult.statistics, statistics)
                if not bIsModeResurrection:
                    xp = statistics.EarnedExperience()
                    player.EarnExperience(xp)
                    bPlayerChanged = True
                if player.nbLevelsUp > 0 and player.levelUpRollResult == 0:
                    player.levelUpRollResult = random.randint(1, 6)
                    player.levelUpRollResult2 = random.randint(1, 6)
                    bPlayerChanged = True
                if hasAging:
                    player.nbMatchsSinceAgeRoll += 1
                    agingMatchPeriod = ServerConfig.Config().GetCachedValue('AgingMatchPeriod', 8)
                    if player.nbMatchsSinceAgeRoll >= agingMatchPeriod:
                        player.ProcessAging()
                    bPlayerChanged = True
            if player.dead == 1:
                if playerResult.statistics.MVP:
                    BB2Achievements.RunAchievementHandlers(team.idCoach, 'BB2Achievements.HandlerSimpleTrigger', ('MvpOnDeadPlayer', ), None)
                try:
                    GetLog(ELogs.General).info('ProcessPostMatchTeamEvolution - Team %d - Removing Dead Player %d Number : %d (%s)', team.ID, player.ID, player.number, player.name.encode('utf-8'))
                except:
                    GetLog(ELogs.General).info('ProcessPostMatchTeamEvolution - Team %d - Removing Dead Player %d Number :%d ', team.ID, player.ID, player.number)

                updatePlayerCount = True
                player.Delete()
            elif bPlayerChanged:
                GetLog(ELogs.General).info('ProcessPostMatchTeamEvolution - Player %d - Number : %d - Xp : %d ', player.ID, player.number, player.experience)
                player.Save()
            if player.retired == 1:
                playerInfos = PlayerListing.GetPlayerInfosMsg(player.ID, False)
                if team.idCoach != 0:
                    if sendRetirementNotif:
                        ServerNotifications.PlayerRetiredNotif(team.idCoach, None, team, playerInfos)
                GetLog(ELogs.General).info('ProcessPostMatchTeamEvolution - Player %d - Number : %d - xp: %d was Retired ', player.ID, player.number, player.experience)
                updatePlayerCount = True
                player.Delete()

        def GetPlayerResult(teamResult, idInMatchPlayer):
            return next(playerResult for playerResult in teamResult.playerResults if playerResult.playerData.id == idInMatchPlayer)

        for idJourneymanToBuy in teamResult.deferredJourneymanBought:
            playerResult = GetPlayerResult(teamResult, idJourneymanToBuy)
            if playerResult != None:
                team.edited = 0
                team.TryBuyJourneyman(playerResult)
                updatePlayerCount = True

        if updatePlayerCount:
            team.UpdatePlayerCount()
        if matchRecord.idMatchType != EMatchType.FriendlyMulti:
            team.flags |= BB2Data.ETeamFlags.Experienced
        if matchRecord.idMatchType != EMatchType.FriendlyMulti:
            team.flags |= BB2Data.ETeamFlags.Experienced
        team.UpdateLevelUpPending()
        team.ComputeValue()
        team.Save()
        return


def ProcessPostMatchTeamStatitics(category, teamResult, teamMatchStats, playerLookupOnNumber=False, **kwargs):
    idCoach = kwargs.get('idCoach', None)
    if idCoach != None and idCoach != 0:
        if category == 'CARREER':
            if getattr(teamMatchStats, 'inflictedPushOuts', 0) >= 3:
                BB2Achievements.RunAchievementHandlers(idCoach, 'BB2Achievements.HandlerSimpleTrigger', ('BeatIt', ), None)
    teamStats = StatisticsTeam.FindFirst(category=category, idTeamListing=teamResult.idTeam)
    if teamStats == None:
        teamStats = StatisticsTeam()
        teamStats.category = category
        teamStats.idTeamListing = teamResult.idTeam
    teamStats.AddMatchStats(teamMatchStats)
    teamStats.Save()
    for playerResult in teamResult.playerResults:
        if playerResult.statistics.idPlayerListing in [IdJourneyMan, IdFreeJourneyMan]:
            continue
        if playerResult.statistics.sustainedDead == 1:
            continue
        idPlayer = None
        if playerLookupOnNumber:
            playerNumber = playerResult.playerData.number
            player = PlayerListing.FindFirst(number=playerNumber, idTeamListing=teamStats.idTeamListing)
            if player == None:
                GetLog(ELogs.General).error('ProcessPostMatchTeamStatitics Player Number : %d Not Found or not Belonguing to team:%d' % (playerNumber, teamStats.idTeamListing))
                continue
            idPlayer = player.ID
        else:
            idPlayer = playerResult.statistics.idPlayerListing
            if PlayerListing.Count(ID=idPlayer, idTeamListing=teamStats.idTeamListing) != 1:
                GetLog(ELogs.General).error('ProcessPostMatchTeamStatitics Player ID Not Found or not Belonguing to team:%d' % playerResult.statistics.idPlayerListing)
                continue
        playerStats = StatisticsPlayer().FindFirst(category=category, idPlayerListing=idPlayer)
        if playerStats == None:
            playerStats = StatisticsPlayer()
            playerStats.category = category
            playerStats.idPlayerListing = idPlayer
        playerStats.AddMatchStats(playerResult.statistics)
        playerStats.Save()

    return teamStats


def ProcessPostMatchCoachStatitics(idCoach, category, teamResult, teamMatchStats):
    coachStats = StatisticsCoach.FindFirst(category=category, idCoach=idCoach)
    if coachStats == None:
        coachStats = StatisticsCoach()
        coachStats.category = category
        coachStats.idCoach = idCoach
    coachStats.AddMatchStats(teamMatchStats)
    coachStats.Save()
    return coachStats


def ComputeMatchRecordFromReport(completionStatus, report):
    matchResult = report.matchResult
    matchRecord = MatchRecord()
    ShardingManager.AssignFromSharded(matchResult.row, matchRecord)
    matchRecord.ID = 0
    matchRecord.idMatchCompletionStatus = completionStatus.gameCompletionStatus
    matchRecord.idCoachHomeCompletionStatus = completionStatus.coachHomeCompletionStatus
    matchRecord.idCoachAwayCompletionStatus = completionStatus.coachAwayCompletionStatus
    return matchRecord


def GetCoachStatsLabelFromMatchRecord(matchRecord, bbEdition=''):
    coachStatsParams = ServerConfig.Config().GetCachedValue('BBCoachStatsConfig', [])
    statLabels = []
    for param in coachStatsParams:
        statLabel = param.get('label', '')
        if param.get('editionDependant', False) == True:
            if bbEdition == '':
                GetLog(ELogs.General).error('GetCoachStatsLabelFromMatchReport - editionDependant stats %s - no edition provided' % statLabel)
                continue
            statLabel += '_%s' % bbEdition
        filterFn = param.get('filterFn', '')
        try:
            if filterFn == '' or eval(filterFn)(matchRecord):
                statLabels.append(statLabel)
        except Exception as e:
            GetLog(ELogs.General).error('GetCoachStatsLabelFromMatchReport - Failed evaluation :\n%s' % traceback.format_exc())

    return statLabels


def CmpEq(lh, rh):
    return lh == rh


def CmpLTE(lh, rh):
    return lh <= rh


def CmpGTE(lh, rh):
    return lh >= rh


OperatorMappings = {'=': CmpEq, '<=': CmpLTE, '>=': CmpGTE}

def UpdateUnlockedAchievements(idCoach, matchRecord):
    idTeam = 0
    if idCoach == matchRecord.idCoachHome:
        coachMatchStats = matchRecord.GetTeamStats('home')
        idTeam = matchRecord.idTeamListingHome
    else:
        if idCoach == matchRecord.idCoachAway:
            coachMatchStats = matchRecord.GetTeamStats('away')
            idTeam = matchRecord.idTeamListingAway
        else:
            raise Exception('InvalidCoachId')
        unlockeds = []
        query = ' SELECT * FROM bb_stats_achievements \n                WHERE ID NOT IN \n                (SELECT idAchievement FROM bb_coach_stats_achievements WHERE idCoach=%s)'
        rowsUncompleted = DBManager().Query(query, idCoach)
        dboCoachStats = StatisticsCoach.Find(idCoach=idCoach)
        dboTeamStats = StatisticsTeam.Find(idTeamListing=idTeam)
        matchStatCategoriesWithSeason = matchRecord.statsCategories.split('|')
        matchStatCategories = []
        for category in matchStatCategoriesWithSeason:
            matchStatCategories.append(category.split('-')[0])

        def MergeStats(mergeDict, statsDbos):
            for statsDbo in statsDbos:
                categoryTokens = statsDbo.category.split('-')
                categoryWithoutSeason = categoryTokens[0]
                if not mergeDict.has_key(categoryWithoutSeason):
                    mergeDict[categoryWithoutSeason] = statsDbo
                else:
                    mergeDict[categoryWithoutSeason].AddMatchStats(statsDbo)

        mergedCoachStats = {}
        MergeStats(mergedCoachStats, dboCoachStats)
        mergedTeamStats = {}
        MergeStats(mergedTeamStats, dboTeamStats)

        def CheckAchievementOnStat(statDbo, rowAchivement):
            cmpMethod = CmpGTE
            operator = rowAchivement['operator']
            if OperatorMappings.has_key(operator):
                cmpMethod = OperatorMappings[operator]
            else:
                GetLog(ELogs.General).error('UpdateUnlockedAchievements: Unknown operator : %s' % operator)
            currentStatValue = getattr(statDbo, rowAchivement['statColumn'], 0)
            if cmpMethod(currentStatValue, rowAchivement['threshold']):
                unlocked = BB2DbObjects.CoachStatsAchievements()
                unlocked.idCoach = idCoach
                unlocked.idAchievement = rowUncompleted['ID']
                unlocked.Save()
                unlockeds.append(rowUncompleted)

        for rowUncompleted in rowsUncompleted:
            category = rowUncompleted['statCategory']
            statsType = 'COACH'
            statsDboChecked = None
            categoryTokens = category.split('/')
            if len(categoryTokens) > 1 and categoryTokens[0] in ('MATCH', 'TEAM', 'COACH'):
                statsType = categoryTokens[0]
                category = categoryTokens[1]
            if category not in matchStatCategories:
                continue
            bDoCheck = True
            if statsType == 'COACH':
                if not mergedCoachStats.has_key(category):
                    continue
                statsDboChecked = mergedCoachStats[category]
            elif statsType == 'TEAM':
                if not mergedTeamStats.has_key(category):
                    continue
                statsDboChecked = mergedTeamStats[category]
            elif statsType == 'MATCH':
                statsDboChecked = coachMatchStats
                if statsDboChecked.wins == 0:
                    bDoCheck = False
            if statsDboChecked != None and bDoCheck:
                CheckAchievementOnStat(statsDboChecked, rowUncompleted)

    return unlockeds


def GetLeaderBoardsUpdate(idCoach, matchRecord):
    coachStats = None
    leaderBoardsUpdates = []
    if idCoach == matchRecord.idCoachHome:
        coachStats = matchRecord.GetTeamStats('home')
    else:
        if idCoach == matchRecord.idCoachAway:
            coachStats = matchRecord.GetTeamStats('away')
        else:
            raise Exception('InvalidCoachId')
        matchStatCategoriesWithSeason = matchRecord.statsCategories.split('|')
        matchStatCategories = []
        for category in matchStatCategoriesWithSeason:
            matchStatCategories.append(category.split('-')[0])

        dboLeaderBoards = BB2DbObjects.StatsLeaderboards().Find()
        for dboLeaderBoard in dboLeaderBoards:
            if dboLeaderBoard.statCategory in matchStatCategories and hasattr(coachStats, dboLeaderBoard.statColumn):
                leaderBoardsUpdates.append((dboLeaderBoard.label, getattr(coachStats, dboLeaderBoard.statColumn, 0)))

    return leaderBoardsUpdates


def GetPredefinedRowTeamsMsgs():
    results = []
    debugTeamPrefixes = ServerConfig.Config().GetCachedValue('BBDebugTeamPrefixes', ['[DEBUG]'])
    query = ' SELECT bb_team_listing.* \n                FROM bb_team_listing \n                WHERE bb_team_listing.deleted=0 \n                AND bb_team_listing.predefined = 1 '
    if len(debugTeamPrefixes) > 0:
        searchClauses = []
        for prefix in debugTeamPrefixes:
            searchClauses.append("(bb_team_listing.name LIKE '%s%%')" % prefix)

        query += 'AND ( (bb_team_listing.active=1) OR (%s)) ' % ('OR').join(searchClauses)
    else:
        query += 'AND bb_team_listing.active=1 '
    query += 'ORDER BY value,IdRaces'
    rowTeams = DBManager().Query(query)
    dicRacesPlayerTypes = {}
    idTeams = [ x['ID'] for x in rowTeams ]
    dicStructures = GetTeamsStadiumStructuresIds(idTeams)
    for rowTeam in rowTeams:
        idTeam = rowTeam['ID']
        if dicStructures.has_key(idTeam):
            structures = dicStructures[idTeam]
            if len(structures) > 0:
                rowTeam['stadiumInfrastructure'] = structures[0]['ID']
        if rowTeam['created'] == None or rowTeam['value'] == 0 or rowTeam['nbPlayers'] == 0 or rowTeam['validated'] == 0:
            GetLog(ELogs.General).info('Updating Predefined Team : %s', rowTeam['name'].encode('utf-8'))
            dboTeam = TeamListing()
            Utils.Assign(rowTeam, dboTeam)
            dboPlayers = PlayerListing.Find(idTeamListing=dboTeam.ID)
            idRaces = dboTeam.IdRaces
            if not dicRacesPlayerTypes.has_key(idRaces):
                dicRacesPlayerTypes[0] = Race.GetPlayerTypesInfo(0)
                dicRacesPlayerTypes[idRaces] = Race.GetPlayerTypesInfo(idRaces)
            for dboPlayer in dboPlayers:
                rowPlayerTypeInfos = None
                playerRace = idRaces
                if dicRacesPlayerTypes[idRaces].has_key(dboPlayer.idPlayerTypes):
                    rowPlayerTypeInfos = dicRacesPlayerTypes[idRaces][dboPlayer.idPlayerTypes]
                elif dicRacesPlayerTypes[0].has_key(dboPlayer.idPlayerTypes):
                    playerRace = 0
                    rowPlayerTypeInfos = dicRacesPlayerTypes[0][dboPlayer.idPlayerTypes]
                else:
                    GetLog(ELogs.General).error('Player %d - %s - RowPlayerType Not found', dboPlayer.ID, dboPlayer.name.encode('utf-8'))
                dboPlayer.IdRaces = playerRace
                dboPlayer.ComputeValue()
                dboPlayer.Save()

            dboTeam.created = datetime.utcnow()
            dboTeam.ComputeValue()
            dboTeam.UpdatePlayerCount()
            dboTeam.levelupPending = 0
            dboTeam.validated = 1
            dboTeam.Save()
            GetLog(ELogs.General).info('Updating Predefined Team : %s - %d - Value : %d', dboTeam.name.encode('utf-8'), dboTeam.ID, dboTeam.value)
        msgTeam = BB2DbRowsMsg.RowTeam()
        ShardingManager.AssignToSharded(rowTeam, msgTeam)
        results.append(msgTeam)

    return results


def GetTeamCoachOverView(idCoach, onlyActive=False):
    results = []
    query = " SELECT bb_team_listing.*,\n                COALESCE(bb_league_team_registration.idLeague,0) as idLeague,COALESCE(bb_competition.idLeague,0) as idLastCompetitionLeague,\n                COALESCE(registrationStatus,%s) as leagueRegistrationStatus,\n                COALESCE(bb_competition_team.idCompetition,0) as idCompetition,COALESCE(bb_competition_team.idTeamCompetitionStatus,%s) as competitionRegistrationStatus,\n                COALESCE(bb_team_solo.soloData,'') as soloData\n                FROM bb_team_listing \n                LEFT JOIN bb_league_team_registration \n                     ON bb_league_team_registration.idTeam=bb_team_listing.ID\n                     AND bb_league_team_registration.registrationStatus =%s\n                LEFT JOIN bb_competition_team \n                    ON bb_competition_team.idTeam = bb_team_listing.ID                    \n                LEFT JOIN bb_competition_team bb_competition_team2\n                    ON bb_competition_team2.idTeam = bb_team_listing.ID\n                    AND bb_competition_team2.updated > bb_competition_team.updated\n                LEFT JOIN bb_competition ON bb_competition_team.idCompetition=bb_competition.id\n                LEFT JOIN bb_team_solo ON bb_team_solo.idTeam = bb_team_listing.ID                \n                WHERE idCoach=%s\n                AND bb_competition_team2.idTeam IS NULL\n                AND bb_team_listing.deleted=0                \n                "
    if onlyActive:
        query += ' AND active=1'
    params = (
     BB2Data.ELeagueRegistrationStatus.NotRegistered,
     BB2Data.ECompetitionRegistrationStatus.NotRegistered,
     BB2Data.ELeagueRegistrationStatus.Registered,
     idCoach)
    rowTeams = DBManager().Query(query, params)
    teamIds = [ x['ID'] for x in rowTeams ]
    dicStructures = GetTeamsStadiumStructuresIds(teamIds)
    import LeagueManagement
    rowRankings = LeagueManagement.GetTeamsCurrentCompetitionRankings(teamIds)
    dicRankings = {}
    for rowRanking in rowRankings:
        idTeam = rowRanking['idTeam']
        if not dicRankings.has_key(idTeam):
            dicRankings[idTeam] = []
        dicRankings[idTeam].append(rowRanking)

    for rowTeam in rowTeams:
        keepCompetitionStatus = [
         BB2Data.ECompetitionRegistrationStatus.Registered, BB2Data.ECompetitionRegistrationStatus.CompetitionFinished]
        if rowTeam['competitionRegistrationStatus'] not in keepCompetitionStatus or rowTeam['idLeague'] != rowTeam['idLastCompetitionLeague']:
            rowTeam['idCompetition'] = 0
            rowTeam['leagueRegistrationStatus'] = BB2Data.ELeagueRegistrationStatus.NotRegistered
            rowTeam['competitionRegistrationStatus'] = BB2Data.ECompetitionRegistrationStatus.NotRegistered
        idTeam = rowTeam['ID']
        teamRankings = dicRankings.get(idTeam, [])
        dicTeamAndRanking = {}
        dicTeamAndRanking['team'] = rowTeam
        dicTeamAndRanking['rankings'] = teamRankings
        dicTeamAndRanking['mainRanking'] = None
        if len(teamRankings) > 0:
            dicTeamAndRanking['mainRanking'] = teamRankings[0]
        if dicStructures.has_key(idTeam):
            structures = dicStructures[idTeam]
            if len(structures) > 0:
                rowTeam['stadiumInfrastructure'] = structures[0]['ID']
        results.append(dicTeamAndRanking)

    return results


def GetCoachStats(idCoach):
    query = ' SELECT * FROM bb_statistics_coach WHERE idCoach=%s'
    return DBManager().Query(query, idCoach)


def ResetTeamCurrentCompetitionStats(idTeams):
    if len(idTeams) == 0:
        return
    strIdTeams = Utils.GetStrSepList(idTeams)
    query = "DELETE FROM bb_statistics_teams WHERE idTeamListing IN (%s) AND category='CURRENTCOMPETITION' " % strIdTeams
    DBManager().Query(query)
    query = 'SELECT ID from bb_player_listing WHERE idTeamListing IN(%s)' % strIdTeams
    playersIds = DBManager().Query(query)
    playersIds = [ x['ID'] for x in playersIds ]
    currentPlayerIndex = 0
    playerStep = 256
    if len(playersIds) > 0:
        while True:
            nbPlayerToProcess = min(currentPlayerIndex + playerStep, len(playersIds) - currentPlayerIndex)
            query = "DELETE FROM bb_statistics_players WHERE idPlayerListing IN (%s) AND category='CURRENTCOMPETITION' " % Utils.GetStrSepList(playersIds[currentPlayerIndex:playerStep + nbPlayerToProcess])
            DBManager().Query(query)
            currentPlayerIndex += nbPlayerToProcess
            if currentPlayerIndex >= len(playersIds):
                break


def DeleteRosters(idRosters):
    if len(idRosters) == 0:
        return
    strTeamIds = Utils.GetStrSepList(idRosters)
    rows = DBManager().Query('SELECT ID FROM bb_player_listing WHERE idTeamListing IN (%s)' % strTeamIds)
    DBManager().Query('DELETE FROM bb_league_team_registration WHERE idTeam IN (%s)' % strTeamIds)
    DBManager().Query('DELETE FROM bb_team_campaign_save WHERE idTeam IN (%s)' % strTeamIds)
    DBManager().Query('DELETE FROM bb_competition_team WHERE idTeam IN (%s)' % strTeamIds)
    DBManager().Query('DELETE FROM bb_statistics_teams WHERE idTeamListing IN (%s)' % strTeamIds)
    DBManager().Query('DELETE FROM bb_team_cards WHERE idTeamListing IN (%s)' % strTeamIds)
    DBManager().Query('DELETE FROM bb_team_solo WHERE idTeam IN (%s)' % strTeamIds)
    lstPlayerIds = [ str(x['ID']) for x in rows ]
    strPlayerIds = (',').join(lstPlayerIds)
    if len(lstPlayerIds) > 0:
        DBManager().Query('DELETE FROM bb_player_skills WHERE idPlayerListing IN (%s)' % strPlayerIds)
        DBManager().Query('DELETE FROM bb_player_casualties WHERE idPlayerListing IN (%s)' % strPlayerIds)
        DBManager().Query('DELETE FROM bb_player_listing WHERE id IN (%s)' % strPlayerIds)
        DBManager().Query('DELETE FROM bb_statistics_players WHERE idPlayerListing IN (%s)' % strPlayerIds)
    DBManager().Query('DELETE FROM bb_team_listing WHERE ID IN (%s)' % strTeamIds)


def GetTeamRostersMsgs(idTeams, getAllStats=True, statisticsCategory=['CARREER'], **kwargs):
    teamRostersMsgs = []
    msgRosterClass = kwargs.get('msgRosterClass', BB2Data.TeamRoster)
    getPlayers = kwargs.get('getPlayers', True)
    getCoachProgression = kwargs.get('getCoachProgression', True)
    lang = kwargs.get('lang', None)
    lstRosters = TeamListing.GetRosters(idTeams, getAllStats, statisticsCategory, getPlayers=getPlayers)
    if len(lstRosters) < 1:
        raise PyLobbyException(BBExceptionDesc.TeamNotFound)
    for roster in lstRosters:
        msgRoster = msgRosterClass()
        rosterTeam = roster['team']
        if getCoachProgression:
            import CoachManagement
            idCoach = rosterTeam.idCoach
            if idCoach != 0:
                dboCoachProgression = CoachManagement.EnsureAndGetCoachProgression(idCoach)
                Utils.Assign(dboCoachProgression, msgRoster.coachProgression.rowCoachProgression)
                msgRoster.coachProgression.xpForNextLevel = dboCoachProgression.GetXpForNextLevel()
                msgRoster.coachProgression.xpForCurrentLevel = dboCoachProgression.GetXpForCurrentLevel()
        ShardingManager.AssignToSharded(rosterTeam, msgRoster.team.row)
        if lang != None:
            if ServerConfig.Config().GetCachedValue('BBLocaFromServer', False):
                MiscManager.LocaliseFields(lang.lower(), msgRoster.team.row, ['name', 'leitmotiv', 'background'])
        Utils.Assign(roster['registration'], msgRoster.team)
        msgRoster.team.nbPlayers = rosterTeam.nbPlayers
        msgRoster.team.idCoach = rosterTeam.idCoach
        msgRoster.team.validated = rosterTeam.validated
        msgRoster.team.levelupPending = rosterTeam.levelupPending
        msgRoster.team.stadiumLevel = rosterTeam.stadiumLevel
        msgRoster.team.online = rosterTeam.online
        msgRoster.coachName = roster['coachName']
        if len(roster['competitions']) > 0:
            msgRoster.team.idCompetition = ShardingManager.GetShardedId(roster['competitions'][0]['bb_competition']['id'], LobbyData.ShardedId)
        rowLeague = roster.get('rowLeague', None)
        if rowLeague != None:
            msgRoster.team.idLeague = ShardingManager.GetShardedId(rowLeague['id'], LobbyData.ShardedId)
            ShardingManager.AssignToSharded(rowLeague, msgRoster.rowLeague)
        dboTeam = TeamListing()
        Utils.Assign(rosterTeam, dboTeam)
        msgRoster.team.teamCards = dboTeam.GetTeamCardsByTypeMsgs()
        msgRoster.team.row.idCheerleadersRace = dboTeam.idRaceCheerleader
        dboSoloData = BB2DbObjects.TeamSolo.FindFirst(idTeam=dboTeam.ID)
        if dboSoloData != None:
            soloData = BB2Data.TeamSolo()
            soloData.FromXmlStr(dboSoloData.soloData)
            msgRoster.competitions.append(soloData.teamCompetition)
            msgRoster.rowLeague = soloData.teamCompetition.rowLeague
        teamStatCategories = []
        for stat in roster['stats']:
            msgStats = BB2Data.StatisticsTeam()
            Utils.Assign(stat, msgStats.row)
            msgStats.category = stat.category
            teamStatCategories.append(stat.category)
            msgRoster.team.statistics.append(msgStats)

        def EnsureTeamStatistics(category):
            if (category in statisticsCategory or getAllStats == True) and category not in teamStatCategories:
                msgStats = BB2Data.StatisticsTeam()
                msgStats.row.idTeamListing = rosterTeam.ID
                msgStats.row.category = category
                msgStats.category = category
                msgRoster.team.statistics.append(msgStats)

        EnsureTeamStatistics('CARREER')
        EnsureTeamStatistics('CURRENTCOMPETITION')
        for competitionData in roster['competitions']:
            msgCompetitiondata = BB2Data.TeamCompetitionData()
            ShardingManager.AssignToSharded(competitionData['bb_competition'], msgCompetitiondata.rowCompetition)
            ShardingManager.AssignToSharded(competitionData['bb_league'], msgCompetitiondata.rowLeague)
            msgCompetitiondata.idTeam = msgRoster.team.row.ID
            msgRoster.competitions.append(msgCompetitiondata)

        for ranking in roster['rankings']:
            msgRanking = BB2Data.TeamRanking()
            Utils.Assign(ranking, msgRanking)
            msgRoster.team.rankings.append(msgRanking)

        if roster['mainRanking'] != None:
            Utils.Assign(roster['mainRanking'], msgRoster.team.mainRanking)
        for player in roster['players']:
            msgPlayerInfos = BB2Data.PlayerInfos()
            ShardingManager.AssignToSharded(player['player'], msgPlayerInfos.player.row)
            if lang != None:
                if ServerConfig.Config().GetCachedValue('BBLocaFromServer', False):
                    MiscManager.LocaliseFields(lang.lower(), msgPlayerInfos.player.row, ['name', 'biography'])
            msgPlayerInfos.skills = [ x.idSkillListing for x in player['skills'] ]
            msgPlayerInfos.casualties = [ x.idPlayerCasualtyTypes for x in player['casualties'] ]
            msgRoster.playerInfos.append(msgPlayerInfos)
            playerStatCategories = []
            for stat in player['stats']:
                msgStats = BB2Data.StatisticsPlayer()
                ShardingManager.AssignToSharded(stat, msgStats.row)
                msgStats.category = stat.category
                msgPlayerInfos.statistics.append(msgStats)
                playerStatCategories.append(stat.category)

            def EnsurePlayerStatistics(category):
                if (category in statisticsCategory or getAllStats == True) and category not in playerStatCategories:
                    msgStats = BB2Data.StatisticsPlayer()
                    msgStats.row.idPlayerListing = player['player'].ID
                    msgStats.category = category
                    msgPlayerInfos.statistics.append(msgStats)

            EnsurePlayerStatistics('CARREER')
            EnsurePlayerStatistics('CURRENTCOMPETITION')

        teamRostersMsgs.append(msgRoster)

    return teamRostersMsgs


def GetTeamRosterMsg(idTeam, getAllStats=True, statisticsCategory=['CARREER']):
    teamRostersMsgs = GetTeamRostersMsgs([idTeam], getAllStats, statisticsCategory)
    if len(teamRostersMsgs) < 1:
        raise PyLobbyException(BBExceptionDesc.TeamNotFound)
    return teamRostersMsgs[0]


def GetAvailableRosterNums(idTeam):
    query = 'SELECT number FROM bb_player_listing WHERE idTeamListing=%s'
    rows = DBManager().Query(query, idTeam)
    numbers = [ x['number'] for x in rows ]
    possibleNumbers = range(1, 17)
    available = []
    for num in possibleNumbers:
        if num not in numbers:
            available.append(num)

    return available


def GetTeamsStadiumStructureId(idTeam):
    query = 'SELECT idTeamListing,bb_rules_cards.ID FROM bb_team_cards,bb_rules_cards\n               WHERE bb_team_cards.idCard= bb_rules_cards.ID \n               AND idTeamListing = %s\n               AND IdCardTypes=%s'
    rows = DBManager().Query(query, (idTeam, BB2Data.ECardType.Structure))
    if len(rows) > 0:
        return rows[0]['ID']
    return 0


def GetTeamsStadiumStructuresIds(idTeams):
    if len(idTeams) == 0:
        return {}
    query = 'SELECT idTeamListing,bb_rules_cards.ID FROM bb_team_cards,bb_rules_cards\n               WHERE bb_team_cards.idCard= bb_rules_cards.ID \n               AND idTeamListing IN (%s)\n               AND IdCardTypes=%d' % (Utils.GetStrSepList(idTeams), BB2Data.ECardType.Structure)
    rows = DBManager().Query(query)
    return Utils.Dictionnarize(rows, (lambda x: x['idTeamListing']))


def SetRulesPlayerDataFromDboPlayer(rulesPlayer, dboPlayer, side):
    rulesPlayer.lobbyId = ShardingManager.GetShardedId(dboPlayer.ID)
    rulesPlayer.id = dboPlayer.ID
    rulesPlayer.teamId = side
    rulesPlayer.name = dboPlayer.name
    rulesPlayer.number = dboPlayer.number
    rulesPlayer.ag = dboPlayer.characsAgility
    rulesPlayer.av = dboPlayer.characsArmourValue
    rulesPlayer.ma = dboPlayer.characsMovementAllowance
    rulesPlayer.st = dboPlayer.characsStrength
    rulesPlayer.level = dboPlayer.idPlayerLevels
    rulesPlayer.idPlayerTypes = dboPlayer.idPlayerTypes
    rulesPlayer.idHead = dboPlayer.idHead
    rulesPlayer.experience = dboPlayer.experience


def SetRulesPlayerDataFromRowPlayer(rulesPlayer, rowPlayer, side):
    dboPlayer = PlayerListing()
    Utils.Assign(rowPlayer, dboPlayer)
    SetRulesPlayerDataFromDboPlayer(rulesPlayer, dboPlayer, side)


def GetMatchUUID(idServer, matchRecord):
    return GetMatchUUIDFromProps(idServer, {'teamHomeName': matchRecord.teamHomeName, 'teamAwayName': matchRecord.teamAwayName, 'idMatch': matchRecord.ID})


def GetMatchUUIDFromProps(idServer, props):
    matchUUID = ''
    idMatch = props['idMatch']
    try:
        hexIdServer = '%02x' % idServer
        hexIdMatch = '%08x' % idMatch
        matchUUID = hexIdServer + hexIdMatch
    except Exception as e:
        GetLog(ELogs.General).error('GetMatchUUID - Error : %s', str(e))

    return matchUUID.upper()


def GetMatchIdFromUUID(matchUUID):
    if len(matchUUID) < 10:
        raise Exception('Invalid Match UUID Format')
    return int(matchUUID[2:], 16)