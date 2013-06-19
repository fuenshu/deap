from __future__ import division
import bisect
import copy

try:
    import cPickle as pickle
except ImportError:
    import pickle

from collections import defaultdict
from functools import partial
from itertools import chain
from operator import eq


def identity(obj):
    """Returns directly the argument *obj*.
    """
    return obj

class History(object):
    """The :class:`History` class helps to build a genealogy of all the
    individuals produced in the evolution. It contains two attributes,
    the :attr:`genealogy_tree` that is a dictionary of lists indexed by
    individual, the list contain the indices of the parents. The second
    attribute :attr:`genealogy_history` contains every individual indexed
    by their individual number as in the genealogy tree.
    
    The produced genealogy tree is compatible with `NetworkX
    <http://networkx.lanl.gov/index.html>`_, here is how to plot the genealogy
    tree ::
    
        history = History()
        
        # Decorate the variation operators
        toolbox.decorate("mate", history.decorator)
        toolbox.decorate("mutate", history.decorator)
        
        # Create the population and populate the history
        population = toolbox.population(n=POPSIZE)
        history.update(population)
        
        # Do the evolution, the decorators will take care of updating the
        # history
        # [...]
        
        import matplotlib.pyplot as plt
        import networkx
        
        graph = networkx.DiGraph(history.genealogy_tree)
        graph = graph.reverse()     # Make the grah top-down
        colors = [toolbox.evaluate(history.genealogy_history[i])[0] for i in graph]
        networkx.draw(graph, node_color=colors)
        plt.show()
    
    Using NetworkX in combination with `pygraphviz
    <http://networkx.lanl.gov/pygraphviz/>`_ (dot layout) this amazing
    genealogy tree can be obtained from the OneMax example with a population
    size of 20 and 5 generations, where the color of the nodes indicate there
    fitness, blue is low and red is high.
    
    .. image:: /_images/genealogy.png
       :width: 67%
     
    .. note::
       The genealogy tree might get very big if your population and/or the 
       number of generation is large.
        
    """
    def __init__(self):
        self.genealogy_index = 0
        self.genealogy_history = dict()
        self.genealogy_tree = dict()
        
    def update(self, individuals):
        """Update the history with the new *individuals*. The index present in
        their :attr:`history_index` attribute will be used to locate their
        parents, it is then modified to a unique one to keep track of those
        new individuals. This method should be called on the individuals after
        each variation.
        
        :param individuals: The list of modified individuals that shall be
                            inserted in the history.
        
        If the *individuals* do not have a :attr:`history_index` attribute, 
        the attribute is added and this individual is considered as having no
        parent. This method should be called with the initial population to
        initialize the history.
        
        Modifying the internal :attr:`genealogy_index` of the history or the
        :attr:`history_index` of an individual may lead to unpredictable
        results and corruption of the history.
        """
        try:
            parent_indices = tuple(ind.history_index for ind in individuals)
        except AttributeError:
            parent_indices = tuple()
        
        for ind in individuals:
            self.genealogy_index += 1
            ind.history_index = self.genealogy_index
            self.genealogy_history[self.genealogy_index] = copy.deepcopy(ind)
            self.genealogy_tree[self.genealogy_index] = parent_indices
    
    @property
    def decorator(self):
        """Property that returns an appropriate decorator to enhance the
        operators of the toolbox. The returned decorator assumes that the
        individuals are returned by the operator. First the decorator calls
        the underlying operation and then calls the :func:`update` function
        with what has been returned by the operator. Finally, it returns the
        individuals with their history parameters modified according to the
        update function.
        """
        def decFunc(func):
            def wrapFunc(*args, **kargs):
                individuals = func(*args, **kargs)
                self.update(individuals)
                return individuals
            return wrapFunc
        return decFunc

    def getGenealogy(self, individual, max_depth=float("inf")):
        """Provide the genealogy tree of an *individual*. The individual must
        have an attribute :attr:`history_index` as defined by
        :func:`~deap.tools.History.update` in order to retrieve its associated
        genealogy tree. The returned graph contains the parents up to
        *max_depth* variations before this individual. If not provided
        the maximum depth is up to the begining of the evolution.

        :param individual: The individual at the root of the genealogy tree.
        :param max_depth: The approximate maximum distance between the root
                          (individual) and the leaves (parents), optional.
        :returns: A dictionary where each key is an individual index and the
                  values are a tuple corresponding to the index of the parents.
        """
        gtree = {}
        visited = set()     # Adds memory to the breadth first search
        def genealogy(index, depth):
            if index not in self.genealogy_tree:
                return             
            depth += 1
            if depth > max_depth:
                return
            parent_indices = self.genealogy_tree[index]
            gtree[index] = parent_indices
            for ind in parent_indices:
                if ind not in visited:
                    genealogy(ind, depth)
                visited.add(ind)
        genealogy(individual.history_index, 0)
        return gtree


class Checkpoint(object):
    """A checkpoint is a file containing the state of any object that has been
    hooked. While initializing a checkpoint, add the objects that you want to
    be dumped by appending keyword arguments to the initializer or using the 
    :meth:`add`. 

    In order to use efficiently this module, you must understand properly the
    assignment principles in Python. This module uses the *pointers* you passed
    to dump the object, for example the following won't work as desired ::

        >>> my_object = [1, 2, 3]
        >>> cp = Checkpoint()
        >>> cp.add("my_object", my_object)
        >>> my_object = [3, 5, 6]
        >>> cp.dump(open("example.ecp", "w"))
        >>> cp.load(open("example.ecp", "r"))
        >>> cp["my_object"]
        [1, 2, 3]

    In order to dump the new value of ``my_object`` it is needed to change its
    internal values directly and not touch the *label*, as in the following ::

        >>> my_object = [1, 2, 3]
        >>> cp = Checkpoint()
        >>> cp.add("my_object", my_object)
        >>> my_object[:] = [3, 5, 6]
        >>> cp.dump(open("example.ecp", "w"))
        >>> cp.load(open("example.ecp", "r"))
        >>> cp["my_object"]
        [3, 5, 6]

    """
    def __init__(self):
        self.objects = {}
        self.keys = {}
        self.values = {}

    def add(self, name, object, key=identity):
        """Add an object to the list of objects to be dumped. The object is
        added under the name specified by the argument *name*, the object
        added is *object*, and the *key* argument allow to specify a subpart
        of the object that should be dumped (*key* defaults to an identity key
        that dumps the entire object).
        
        :param name: The name under which the object will be dumped.
        :param object: The object to register for dumping.
        :param key: A function access the subcomponent of the object to dump,
                    optional.
        
        The following illustrates how to use the key.
        ::

            >>> from operator import itemgetter
            >>> my_object = [1, 2, 3]
            >>> cp = Checkpoint()
            >>> cp.add("item0", my_object, key=itemgetter(0))
            >>> cp.dump(open("example.ecp", "w"))
            >>> cp.load(open("example.ecp", "r"))
            >>> cp["item0"]
            1

        """
        self.objects[name] = object
        self.keys[name] = partial(key, object)

    def remove(self, *args):
        """Remove objects with the specified name from the list of objects to
        be dumped.
        
        :param name: The name of one or more object to remove from dumping.
        
        """
        for element in args:
            del self.objects[element]
            del self.keys[element]
            del self.values[element]

    def __getitem__(self, value):
        return self.values.get(value)

    def dump(self, file):
        """Dump the current registered object values in the provided
        *filestream*.
        
        :param filestream: A stream in which write the data.
        """
        self.values = dict.fromkeys(self.objects.iterkeys())
        for name, key in self.keys.iteritems():
            self.values[name] = key()
        pickle.dump(self.values, file)

    def load(self, file):
        """Load a checkpoint from the provided *filestream* retrieving the
        dumped object values, it is not safe to load a checkpoint file in a
        checkpoint object that contains references as all conflicting names
        will be updated with the new values.
        
        :param filestream: A stream from which to read a checkpoint.
        """
        self.values.update(pickle.load(file))

class Statistics(object):
    """Object that compiles statistics on a list of arbitrary objects. 
    When created the statistics object receives a *key* argument that 
    is used to get the values on which the function will be computed. 
    If not provided the *key* argument defaults to the identity function.

    :param key: A function to access the values on which to compute the
                statistics, optional.

    ::
    
        >>> s = Statistics()
        >>> s.register("mean", mean)
        >>> s.register("max", max)
        >>> s.compile([1, 2, 3, 4])
        {"mean" : 2.5, "max" : 4}
        >>> s.compile([5, 6, 7, 8])
        {"mean" : 6.5, "max" : 8}
    """
    def __init__(self, key=identity):
        self.key = key
        self.functions = dict()
        self.fields = []

    def register(self, name, function, *args, **kargs):
        """Register a *function* that will be applied on the sequence each
        time :meth:`record` is called.

        :param name: The name of the statistics function as it would appear
                     in the dictionnary of the statistics object.
        :param function: A function that will compute the desired statistics
                         on the data as preprocessed by the key.
        :param argument: One or more argument (and keyword argument) to pass
                         automatically to the registered function when called,
                         optional.
        """        
        self.functions[name] = partial(function, *args, **kargs)
        self.fields.append(name)

    def compile(self, data):
        """Apply to the input sequence *data* each registered function 
        and return the results as a dictionnary.
        
        :param data: Sequence of objects on which the statistics are computed.
        """
        values = tuple(self.key(elem) for elem in data)
        
        entry = dict()
        for key, func in self.functions.iteritems():
            entry[key] = func(values)
        return entry

class MultiStatistics(dict):
    """Dictionary of :class:`Statistics` object allowing to compute
    statistics on multiple keys using a single call to :meth:`record`. It
    takes a set of key-value pairs associating a statistics object to a
    unique name. This name can then be used to retrieve the statistics object.
    ::

        >>> stats1 = Statistics(key=len)
        >>> stats2 = Statistics(key=attrgetter("fitness.values"))
        >>> mstats = MultStatistics(length=stats1, fitness=stats2)
        >>> mstats.register("mean", numpy.mean, axis=0)
        >>> mstats.register("max", numpy.max)
        >>> mstats.compile(pop)
        {'length' : {'mean' : 2.5, 'max' : 7}, 'fitness' : {'mean' : 1.0, 'max': 5.0}}
    """ 
    def compile(self, data):
        """Calls :meth:`Statistics.compile` with *data* of each
        :class:`Statistics` object.
        
        :param data: Sequence of objects on which the statistics are computed.
        """
        record = {}
        for name, stats in self.items():
            record[name] = stats.compile(data)
        return record

    @property
    def fields(self):
        return list(self.keys())

    def register(self, name, function, *args, **kargs):
        """Register a *function* in each :class:`Statistics` object.
        
        :param name: The name of the statistics function as it would appear
                     in the dictionnary of the statistics object.
        :param function: A function that will compute the desired statistics
                         on the data as preprocessed by the key.
        :param argument: One or more argument (and keyword argument) to pass
                         automatically to the registered function when called,
                         optional.
        """
        for stats in self.values():
            stats.register(name, function, *args, **kargs)

class Logbook(list):
    """Evolution records as a chronological list of dictionary.

    Columns can be retrieved via the *select* method given the appropriate
    names.
    """
    def __init__(self):
        self.buffindex = 0
        self.chapters = defaultdict(Logbook)
        self.header = None
        """Order of the columns to print when using the :meth:`stream` and
        :meth:`__str__` methods. The syntax is a single iterable containing
        string elements. For example, with the previously
        defined statistics class, one can print the generation and the
        fitness average, and maximum with
        ::

            logbook.header = ("gen", "mean", "max")
        
        If not set the header is built with all fields, in arbritrary order
        on insertion of the first data. The header can be removed by setting
        it to :data:`None`.
        """        

    def record(self, **infos):
        for key, value in infos.items():
            if isinstance(value, dict):
                self.chapters[key].record(**value)
                del infos[key]
        self.append(infos)

    def select(self, *names):
        """Return a list of values associated to the *names* provided
        in argument in each dictionary of the Statistics object list.
        One list per name is returned in order.
        ::

            >>> log = Logbook()
            >>> log.append({'gen' : 0, 'mean' : 5.4, 'max' : 10.0})
            >>> log.append({'gen' : 1, 'mean' : 9.4, 'max' : 15.0})
            >>> log.select("mean")
            [5.4, 9.4]
            >>> s.select("gen", "max")
            ([0, 1], [10.0, 15.0])
        """
        if len(names) == 1:
            return [entry.get(names[0], None) for entry in self]
        return tuple([entry.get(name, None) for entry in self] for name in names)

    @property
    def stream(self):
        """Retrieve the formated unstreamed entries of the database including
        the headers.
        ::

            >>> log = Logbook()
            >>> log.append({'gen' : 0})
            >>> print log.stream
            gen
              0
            >>> log.append({'gen' : 1})
            >>> print log.stream
              1
        """
        startindex, self.buffindex = self.buffindex, len(self)
        return self.__str__(startindex)

    def __delitem__(self, key):
        if isinstance(key, slice):
            for i, in range(*key.indices(len(self))):
                self.pop(i)
                for chapter in self.chapters.values():
                    chapter.pop(i)
        else:
            self.pop(key)
            for chapter in self.chapters.values():
                chapter.pop(key)
        
    def pop(self, index=0):
        """Retrieve and delete element *index*. The header and stream will be
        adjusted to follow the modification.

        :param item: The index of the element to remove, optional. It defaults
                     to the first element.
        
        You can also use the following syntax to delete elements.
        ::
        
            del log[0]
            del log[1::5]
        """
        if index < self.buffindex:
            self.buffindex -= 1
        return super(self.__class__, self).pop(index)

    def __txt__(self, startindex):
        columns = self.header
        if not columns:
            columns = self[0].keys() + self.chapters.keys()
        columns_len = map(len, columns)

        chapters_txt = {}
        offsets = defaultdict(int)
        for name, chapter in self.chapters.items():
            chapters_txt[name] = chapter.__txt__(startindex)
            if startindex == 0:
                offsets[name] = len(chapters_txt[name]) - len(self)

        str_matrix = []
        for i, line in enumerate(self[startindex:]):
            str_line = []
            for j, name in enumerate(columns):
                if name in chapters_txt:
                    column = chapters_txt[name][i+offsets[name]]
                else:
                    value = line.get(name, "")
                    string = "{0:n}" if isinstance(value, float) else "{0}"
                    column = string.format(value)
                columns_len[j] = max(columns_len[j], len(column))
                str_line.append(column)
            str_matrix.append(str_line)

        if startindex == 0:
            header = []
            nlines = 1
            if len(self.chapters) > 0:
                nlines += max(map(len, chapters_txt.values())) - len(self) + 1
            header = [[] for i in xrange(nlines)]
            for j, name in enumerate(columns):
                if name in chapters_txt:
                    length = max(len(line.expandtabs()) for line in chapters_txt[name])
                    blanks = nlines - 2 - offsets[name]
                    for i in xrange(blanks):
                        header[i].append(" " * length)
                    header[blanks].append(name.center(length))
                    header[blanks+1].append("-" * length)
                    for i in xrange(offsets[name]):
                        header[blanks+2+i].append(chapters_txt[name][i])
                else:
                    length = max(len(line[j].expandtabs()) for line in str_matrix)
                    for line in header[:-1]:
                        line.append(" " * length)
                    header[-1].append(name)
            str_matrix = chain(header, str_matrix)

        template = "\t".join("{%i:<%i}" % (i, l) for i, l in enumerate(columns_len))
        text = [template.format(*line) for line in str_matrix]
        return text

    def __str__(self, startindex=0):
        text = self.__txt__(startindex)
        return "\n".join(text)


class HallOfFame(object):
    """The hall of fame contains the best individual that ever lived in the
    population during the evolution. It is lexicographically sorted at all
    time so that the first element of the hall of fame is the individual that
    has the best first fitness value ever seen, according to the weights
    provided to the fitness at creation time.
    
    The insertion is made so that old individuals have priority on new
    individuals. A single copy of each individual is kept at all time, the
    equivalence between two individuals is made by the operator passed to the
    *similar* argument.

    :param maxsize: The maximum number of individual to keep in the hall of
                    fame.
    :param similar: An equivalence operator between two individuals, optional.
                    It defaults to operator :func:`operator.eq`.
    
    The class :class:`HallOfFame` provides an interface similar to a list
    (without being one completely). It is possible to retrieve its length, to
    iterate on it forward and backward and to get an item or a slice from it.
    """
    def __init__(self, maxsize, similar=eq):
        self.maxsize = maxsize
        self.keys = list()
        self.items = list()
        self.similar = similar
    
    def update(self, population):
        """Update the hall of fame with the *population* by replacing the
        worst individuals in it by the best individuals present in
        *population* (if they are better). The size of the hall of fame is
        kept constant.
        
        :param population: A list of individual with a fitness attribute to
                           update the hall of fame with.
        """
        if len(self) == 0 and self.maxsize !=0:
            # Working on an empty hall of fame is problematic for the
            # "for else"
            self.insert(population[0])
        
        for ind in population:
            if ind.fitness > self[-1].fitness or len(self) < self.maxsize:
                for hofer in self:
                    # Loop through the hall of fame to check for any
                    # similar individual
                    if self.similar(ind, hofer):
                        break
                else:
                    # The individual is unique and strictly better than
                    # the worst
                    if len(self) >= self.maxsize:
                        self.remove(-1)
                    self.insert(ind)
    
    def insert(self, item):
        """Insert a new individual in the hall of fame using the
        :func:`~bisect.bisect_right` function. The inserted individual is
        inserted on the right side of an equal individual. Inserting a new 
        individual in the hall of fame also preserve the hall of fame's order.
        This method **does not** check for the size of the hall of fame, in a
        way that inserting a new individual in a full hall of fame will not
        remove the worst individual to maintain a constant size.
        
        :param item: The individual with a fitness attribute to insert in the
                     hall of fame.
        """
        item = copy.deepcopy(item)
        i = bisect.bisect_right(self.keys, item.fitness)
        self.items.insert(len(self) - i, item)
        self.keys.insert(i, item.fitness)
    
    def remove(self, index):
        """Remove the specified *index* from the hall of fame.
        
        :param index: An integer giving which item to remove.
        """
        del self.keys[len(self) - (index % len(self) + 1)]
        del self.items[index]
    
    def clear(self):
        """Clear the hall of fame."""
        del self.items[:]
        del self.keys[:]

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        return self.items[i]

    def __iter__(self):
        return iter(self.items)

    def __reversed__(self):
        return reversed(self.items)
    
    def __str__(self):
        return str(self.items)


class ParetoFront(HallOfFame):
    """The Pareto front hall of fame contains all the non-dominated individuals
    that ever lived in the population. That means that the Pareto front hall of
    fame can contain an infinity of different individuals.
    
    :param similar: A function that tels the Pareto front whether or not two
                    individuals are similar, optional.
    
    The size of the front may become very large if it is used for example on
    a continuous function with a continuous domain. In order to limit the number
    of individuals, it is possible to specify a similarity function that will
    return :data:`True` if the genotype of two individuals are similar. In that
    case only one of the two individuals will be added to the hall of fame. By
    default the similarity function is :func:`operator.__eq__`.
    
    Since, the Pareto front hall of fame inherits from the :class:`HallOfFame`, 
    it is sorted lexicographically at every moment.
    """
    def __init__(self, similar=eq):
        HallOfFame.__init__(self, None, similar)
    
    def update(self, population):
        """Update the Pareto front hall of fame with the *population* by adding 
        the individuals from the population that are not dominated by the hall
        of fame. If any individual in the hall of fame is dominated it is
        removed.
        
        :param population: A list of individual with a fitness attribute to
                           update the hall of fame with.
        """
        for ind in population:
            is_dominated = False
            has_twin = False
            to_remove = []
            for i, hofer in enumerate(self):    # hofer = hall of famer
                if hofer.fitness.dominates(ind.fitness):
                    is_dominated = True
                    break
                elif ind.fitness.dominates(hofer.fitness):
                    to_remove.append(i)
                elif ind.fitness == hofer.fitness and self.similar(ind, hofer):
                    has_twin = True
                    break
            
            for i in reversed(to_remove):       # Remove the dominated hofer
                self.remove(i)
            if not is_dominated and not has_twin:
                self.insert(ind)

__all__ = ['HallOfFame', 'ParetoFront', 'History', 'Statistics', 'MultiStatistics', 'Logbook', 'Checkpoint']

if __name__ == "__main__":
    doctest.run_docstring_examples(Statistics.register, globals())
    doctest.run_docstring_examples(Statistics.compile, globals())

